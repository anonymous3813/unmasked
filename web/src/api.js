const TOKEN_KEY = "unmaskedToken";
const ACCOUNT_KEY = "unmaskedAccount";

export function readSession() {
  let account = null;
  try {
    account = JSON.parse(localStorage.getItem(ACCOUNT_KEY) || "null");
  } catch (error) {
    account = null;
  }
  return { token: localStorage.getItem(TOKEN_KEY) || "", account };
}

export function saveSession(token, account) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(ACCOUNT_KEY, JSON.stringify(account || {}));
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(ACCOUNT_KEY);
}

function headers() {
  const { token } = readSession();
  const result = { "Content-Type": "application/json" };
  if (token) result.Authorization = "Bearer " + token;
  return result;
}

export async function api(path, options = {}) {
  const response = await fetch(path, {
    method: options.method || "GET",
    headers: headers(),
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const payload = await response.json().catch(() => ({}));
  if (response.status === 401) {
    const error = new Error(payload.detail || "Sign in to use Unmasked.");
    error.status = 401;
    throw error;
  }
  if (!response.ok) {
    throw new Error(payload.detail || "The request did not go through.");
  }
  return payload;
}
