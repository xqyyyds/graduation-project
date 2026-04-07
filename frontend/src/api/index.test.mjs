import assert from "node:assert/strict";
import { deriveWsUrl, normalizeBaseUrl } from "./index.js";

assert.equal(
  normalizeBaseUrl("http://localhost:8000/"),
  "http://localhost:8000"
);
assert.equal(
  normalizeBaseUrl(" https://demo.example.com/api/v1/ "),
  "https://demo.example.com/api/v1"
);
assert.equal(
  deriveWsUrl("http://localhost:8000/"),
  "ws://localhost:8000/ws/logs"
);
assert.equal(
  deriveWsUrl("https://demo.example.com"),
  "wss://demo.example.com/ws/logs"
);

console.log("api index tests passed");
