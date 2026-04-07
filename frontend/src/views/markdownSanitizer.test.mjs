import assert from "node:assert/strict";
import { sanitizeRenderedMarkdown } from "./markdownSanitizer.js";

const unsafe = `
<p onclick="alert('x')">safe</p>
<script>alert('boom')</script>
<a href="javascript:alert('x')">click</a>
<iframe src="https://evil.example"></iframe>
`;

const sanitized = sanitizeRenderedMarkdown(unsafe);

assert.equal(sanitized.includes("<script>"), false);
assert.equal(sanitized.includes("onclick="), false);
assert.equal(sanitized.includes("javascript:"), false);
assert.equal(sanitized.includes("<iframe"), false);
assert.equal(sanitized.includes("<p>safe</p>"), true);

console.log("markdownSanitizer tests passed");
