# Browser security checks

Check the exact API and browser behavior before reporting a security finding.
This focused reference is not a complete browser security standard.

## Event handlers

An event-handler content attribute such as setAttribute("onclick", text) treats
text as handler source. Assigning a string to the onclick IDL property does not
compile that string as JavaScript; event-handler callbacks use
LegacyTreatNonObjectAsNull. Do not equate those two APIs.
[HTML event handlers](https://html.spec.whatwg.org/multipage/webappapis.html#event-handlers)

## CORS

For credentials mode include, Access-Control-Allow-Origin: * does not permit the
browser to share the response, even with Access-Control-Allow-Credentials: true.
A rejected response is not proof that a request had no side effect. Investigate
CSRF and origin-reflection behavior separately; do not label this header pair
alone as credentialed data exposure.
[Fetch CORS and credentials](https://fetch.spec.whatwg.org/#cors-protocol-and-credentials)

## Content Security Policy

Choose a policy for the application's actual resource and navigation needs.
A nonce-bearing script-src directive does not replace base-uri: an injected base
element can retarget a relative script URL. Restrict base-uri appropriately
(often 'none' or 'self'). Evaluate object-src, form-action, frame-ancestors and
other relevant directives for the distinct boundaries they control.
Do not remove those protections merely for development convenience, or present a
single script directive as a complete policy.
[CSP Level 3](https://www.w3.org/TR/CSP3/)

## Cross-document messages

Use an exact target origin when it exists. Some intended recipients have opaque
origins, requiring a wildcard target. In that case do not send sensitive data;
validate the expected window source and message shape, account for navigation,
and design authentication appropriate to the channel. A serialized null origin
alone is not proof of sender identity. A window reference alone does not prove
which document it now contains.
[HTML cross-document messaging](https://html.spec.whatwg.org/multipage/web-messaging.html#crossDocumentMessages)

For other browser features, consult their current official specifications or
browser documentation and verify the application's observable behavior.
