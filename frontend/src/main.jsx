import React, {createContext, useContext, useEffect, useState} from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import {api, setToken, token} from './lib/api';
import './styles.css';

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

function AuthProvider({children}) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    if (!token()) { setLoading(false); return; }
    api('/api/me').then(setUser).catch(() => setToken(null)).finally(() => setLoading(false));
  }, []);
  const login = (data) => { setToken(data.token); setUser(data.user); };
  const logout = () => { setToken(null); setUser(null); };
  return <AuthContext.Provider value={{user, loading, login, logout}}>{children}</AuthContext.Provider>;
}

createRoot(document.getElementById('root')).render(<BrowserRouter><AuthProvider><App /></AuthProvider></BrowserRouter>);
