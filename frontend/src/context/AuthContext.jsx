import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { authService } from '../services/authService';
import { setAuthToken } from '../services/api';

const AuthContext = createContext();

export function AuthProvider({ children }) {
  const [token, setToken] = useState('');
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const initAuth = async () => {
      if (!token) {
        setAuthToken('');
        setLoading(false);
        return;
      }

      try {
        setAuthToken(token);
        const res = await authService.getProfile();
        setUser(res.user || null);
      } catch (error) {
        setAuthToken('');
        setToken('');
        setUser(null);
      } finally {
        setLoading(false);
      }
    };

    initAuth();
  }, [token]);

  const login = async (email, password) => {
    const response = await authService.login(email, password);
    if (response.token) {
      setAuthToken(response.token);
      setToken(response.token);
      setUser(response.user || null);
      return response;
    }
    throw new Error(response.message || 'Login failed');
  };

  const register = async (name, email, password) => {
    const response = await authService.register(name, email, password);
    if (response.token) {
      setAuthToken(response.token);
      setToken(response.token);
      setUser(response.user || null);
      return response;
    }
    throw new Error(response.message || 'Registration failed');
  };

  const logout = () => {
    setAuthToken('');
    setToken('');
    setUser(null);
  };

  const value = useMemo(
    () => ({
      token,
      user,
      loading,
      isAuthenticated: Boolean(token),
      login,
      register,
      logout,
    }),
    [token, user, loading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
