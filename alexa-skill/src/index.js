"use strict";

const Alexa = require("ask-sdk-core");

const BACKEND_URL = process.env.BACKEND_URL;
const BACKEND_TOKEN = process.env.BACKEND_TOKEN;

async function callBackend(text, history = []) {
  if (!BACKEND_URL || !BACKEND_TOKEN) {
    throw new Error("BACKEND_URL ou BACKEND_TOKEN não configurado.");
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);

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
        .speak(data.reply)
        .reprompt(
          "Continue by beginning your answer with, I say."
        )
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
    const requestType = Alexa.getRequestType(
      handlerInput.requestEnvelope
    );

    if (requestType === "SessionEndedRequest") {
      return true;
    }

    if (requestType !== "IntentRequest") {
      return false;
    }

    const intentName = Alexa.getIntentName(
      handlerInput.requestEnvelope
    );

    return [
      "AMAZON.StopIntent",
      "AMAZON.CancelIntent",
    ].includes(intentName);
  },

  handle(handlerInput) {
    return handlerInput.responseBuilder
      .speak("Goodbye. See you next time.")
      .withShouldEndSession(true)
      .getResponse();
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
    FallbackIntentHandler
  )
  .addErrorHandlers(ErrorHandler)
  .lambda();
