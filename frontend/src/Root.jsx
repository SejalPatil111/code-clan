import { useCallback, useEffect, useState } from "react";
import App from "./App.jsx";
import LoginPage from "./components/LoginPage.jsx";
import { clearSession, fetchMe, getStoredSession, setUnauthorizedHandler, storeSession } from "./api";

/**
 * Auth gate: shows the login page when signed out, otherwise renders the
 * role-aware App for the authenticated user.
 */
export default function Root() {
  const [session, setSession] = useState(() => getStoredSession());

  const logout = useCallback(() => {
    clearSession();
    setSession(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(logout);
  }, [logout]);

  // Re-validate a stored session on load (token may have expired or role changed).
  const storedToken = session?.token;
  useEffect(() => {
    if (!storedToken) return;
    fetchMe()
      .then((user) => {
        storeSession(storedToken, user);
        setSession((prev) => (prev ? { ...prev, user } : prev));
      })
      .catch(() => logout());
  }, [storedToken, logout]);

  const handleAuthenticated = (token, user) => {
    storeSession(token, user);
    setSession({ token, user });
  };

  if (!session) {
    return <LoginPage onAuthenticated={handleAuthenticated} />;
  }

  // key forces a clean App state when a different user logs in
  return <App key={session.user.id} currentUser={session.user} onLogout={logout} />;
}
