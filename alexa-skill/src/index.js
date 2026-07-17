"use strict";

const crypto = require("crypto");
const Alexa = require("ask-sdk-core");

const BACKEND_URL = process.env.BACKEND_URL;
const BACKEND_TOKEN = process.env.BACKEND_TOKEN;
const BACKEND_LOG_URL =
  process.env.BACKEND_LOG_URL ||
  (BACKEND_URL
    ? BACKEND_URL.replace(/\/respond\/?$/, "/interactions/")
    : "");

function escapeSsml(text = "") {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

async function callBackend(text, history = []) {
  if (!BACKEND_URL || !BACKEND_TOKEN) {
    throw new Error("BACKEND_URL ou BACKEND_TOKEN não configurado.");
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5500);

  try {
    const response = await fetch(BACKEND_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Alexa-Token": BACKEND_TOKEN,
      },
      body: JSON.stringify({
        text,
        history,
      }),
      signal: controller.signal,
    });

    const rawBody = await response.text();

    if (!response.ok) {
      throw new Error(
        `Backend respondeu ${response.status}: ${rawBody}`
      );
    }

    const data = JSON.parse(rawBody);

    if (!data.reply || typeof data.reply !== "string") {
      throw new Error("Backend não retornou o campo reply.");
    }

    return data;
  } finally {
    clearTimeout(timeout);
  }
}

function extractSlots(request) {
  const requestSlots = request?.intent?.slots || {};
  const slots = {};

  for (const [name, slot] of Object.entries(requestSlots)) {
    slots[name] = {
      value: slot?.value || "",
      confirmationStatus: slot?.confirmationStatus || "NONE",
      resolutions: slot?.resolutions || null,
    };
  }

  return slots;
}

function extractSpeech(response) {
  const outputSpeech = response?.outputSpeech;

  if (!outputSpeech) {
    return "";
  }

  if (outputSpeech.type === "PlainText") {
    return outputSpeech.text || "";
  }

  if (outputSpeech.type === "SSML") {
    return (outputSpeech.ssml || "")
      .replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  return "";
}

function hashUserId(userId) {
  if (!userId || !BACKEND_TOKEN) {
    return "";
  }

  return crypto
    .createHmac("sha256", BACKEND_TOKEN)
    .update(userId)
    .digest("hex");
}

async function logInteraction(handlerInput, response) {
  if (!BACKEND_LOG_URL || !BACKEND_TOKEN) {
    console.warn(
      "Registro Alexa desativado: BACKEND_LOG_URL ou BACKEND_TOKEN ausente."
    );
    return;
  }

  const envelope = handlerInput.requestEnvelope || {};
  const request = envelope.request || {};
  const session = envelope.session || {};
  const system = envelope.context?.System || {};
  const applicationId =
    session.application?.applicationId ||
    system.application?.applicationId ||
    "";
  const userId =
    session.user?.userId ||
    system.user?.userId ||
    "";
  const sessionId = session.sessionId || request.requestId || "";
  const userText = request.intent?.slots?.text?.value || "";

  const payload = {
    request_id: request.requestId || "",
    session_id: sessionId,
    application_id: applicationId,
    user_id_hash: hashUserId(userId),
    request_type: request.type || "",
    intent_name: request.intent?.name || "",
    locale: request.locale || "",
    slots: extractSlots(request),
    user_text: userText,
    assistant_text: extractSpeech(response),
    session_ended_reason: request.reason || "",
    request_data: request,
  };

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 1500);

  try {
    const logResponse = await fetch(BACKEND_LOG_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Alexa-Token": BACKEND_TOKEN,
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });

    if (!logResponse.ok) {
      const rawBody = await logResponse.text();
      throw new Error(
        `Logger respondeu ${logResponse.status}: ${rawBody}`
      );
    }
  } finally {
    clearTimeout(timeout);
  }
}

const InteractionLoggingResponseInterceptor = {
  async process(handlerInput, response) {
    try {
      await logInteraction(handlerInput, response);
    } catch (error) {
      // O registro não deve impedir a Alexa de responder ao usuário.
      console.error("Erro ao registrar interação no backend:", error);
    }
  },
};

const LaunchRequestHandler = {
  canHandle(handlerInput) {
    return (
      Alexa.getRequestType(handlerInput.requestEnvelope) ===
      "LaunchRequest"
    );
  },

  handle(handlerInput) {
    handlerInput.attributesManager.setSessionAttributes({
      history: [],
    });

    const speech =
      "Welcome to English Buddy. " +
      "Let's practice English. " +
      "Begin each answer with the words, I say. " +
      "What did you do today?";

    return handlerInput.responseBuilder
      .speak(speech)
      .reprompt(
        "Begin your answer with, I say. " +
        "For example, I say I worked today."
      )
      .getResponse();
  },
};

const ConversationIntentHandler = {
  canHandle(handlerInput) {
    return (
      Alexa.getRequestType(handlerInput.requestEnvelope) ===
        "IntentRequest" &&
      Alexa.getIntentName(handlerInput.requestEnvelope) ===
        "ConversationIntent"
    );
  },

  async handle(handlerInput) {
    const text = Alexa.getSlotValue(
      handlerInput.requestEnvelope,
      "text"
    );

    if (!text || !text.trim()) {
      return handlerInput.responseBuilder
        .speak(
          "I did not understand. Please begin with, I say."
        )
        .reprompt(
          "For example, I say I had a busy day."
        )
        .getResponse();
    }

    const sessionAttributes =
      handlerInput.attributesManager.getSessionAttributes();

    const history = Array.isArray(sessionAttributes.history)
      ? sessionAttributes.history
      : [];

    try {
      const data = await callBackend(text.trim(), history);

      handlerInput.attributesManager.setSessionAttributes({
        ...sessionAttributes,
        history: Array.isArray(data.history)
          ? data.history
          : history,
      });

      return handlerInput.responseBuilder
        .speak(escapeSsml(data.reply))
        .reprompt(
          "Continue by beginning your answer with, I say."
        )
        .withShouldEndSession(false)
        .getResponse();
    } catch (error) {
      console.error("Erro ao chamar o backend:", error);

      return handlerInput.responseBuilder
        .speak(
          "Sorry, I could not reach English Buddy. " +
          "Please check that the backend is online."
        )
        .reprompt(
          "Try again by beginning your answer with, I say."
        )
        .getResponse();
    }
  },
};

const HelpIntentHandler = {
  canHandle(handlerInput) {
    return (
      Alexa.getRequestType(handlerInput.requestEnvelope) ===
        "IntentRequest" &&
      Alexa.getIntentName(handlerInput.requestEnvelope) ===
        "AMAZON.HelpIntent"
    );
  },

  handle(handlerInput) {
    const speech =
      "Talk to me in English. " +
      "Begin your answer with, I say. " +
      "For example, I say I went to work today.";

    return handlerInput.responseBuilder
      .speak(speech)
      .reprompt(speech)
      .getResponse();
  },
};

const StopIntentHandler = {
  canHandle(handlerInput) {
    return (
      Alexa.getRequestType(handlerInput.requestEnvelope) ===
        "IntentRequest" &&
      [
        "AMAZON.StopIntent",
        "AMAZON.CancelIntent",
      ].includes(
        Alexa.getIntentName(handlerInput.requestEnvelope)
      )
    );
  },

  handle(handlerInput) {
    return handlerInput.responseBuilder
      .speak("Goodbye. See you next time.")
      .withShouldEndSession(true)
      .getResponse();
  },
};

const SessionEndedRequestHandler = {
  canHandle(handlerInput) {
    return (
      Alexa.getRequestType(handlerInput.requestEnvelope) ===
      "SessionEndedRequest"
    );
  },

  handle(handlerInput) {
    const request = handlerInput.requestEnvelope.request;

    console.log(
      "SESSION_ENDED",
      JSON.stringify({
        requestId: request.requestId,
        reason: request.reason,
        error: request.error || null,
      })
    );

    // SessionEndedRequest exige resposta vazia.
    return handlerInput.responseBuilder.getResponse();
  },
};

const FallbackIntentHandler = {
  canHandle(handlerInput) {
    return (
      Alexa.getRequestType(handlerInput.requestEnvelope) ===
        "IntentRequest" &&
      Alexa.getIntentName(handlerInput.requestEnvelope) ===
        "AMAZON.FallbackIntent"
    );
  },

  handle(handlerInput) {
    return handlerInput.responseBuilder
      .speak(
        "I did not understand. Begin your sentence with, I say."
      )
      .reprompt(
        "For example, I say I had a good day."
      )
      .getResponse();
  },
};

const ErrorHandler = {
  canHandle() {
    return true;
  },

  handle(handlerInput, error) {
    console.error("Erro não tratado:", error);

    return handlerInput.responseBuilder
      .speak(
        "Sorry, something went wrong. Please try again."
      )
      .reprompt(
        "Begin your answer with, I say."
      )
      .getResponse();
  },
};

exports.handler = Alexa.SkillBuilders.custom()
  .addRequestHandlers(
    LaunchRequestHandler,
    ConversationIntentHandler,
    HelpIntentHandler,
    StopIntentHandler,
    SessionEndedRequestHandler,
    FallbackIntentHandler
  )
  .addResponseInterceptors(InteractionLoggingResponseInterceptor)
  .addErrorHandlers(ErrorHandler)
  .lambda();
