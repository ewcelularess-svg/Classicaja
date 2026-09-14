import React from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import Header from './components/Header';
import BottomNav from './components/BottomNav';
import Home from './pages/Home';
import Product from './pages/Product';
import Publish from './pages/Publish';
import Auth from './pages/Auth';
import MyAds from './pages/MyAds';
import Favorites from './pages/Favorites';
import Dashboard from './pages/Dashboard';
import Chat from './pages/Chat';
import Boost from './pages/Boost';
import Admin from './pages/Admin';
import { useAuth } from './main';

function Protected({children}) {
  const {user, loading} = useAuth();
  if (loading) return <div className="loading">Carregando...</div>;
  return user ? children : <Navigate to="/entrar" />;
}
function AdminOnly({children}) {
  const {user, loading} = useAuth();
  if (loading) return <div className="loading">Carregando...</div>;
  return user?.role === 'admin' ? children : <Navigate to="/" />;
}
export default function App(){
  return <div className="app"><Header/><main><Routes>
    <Route path="/" element={<Home/>}/>
    <Route path="/produto/:id" element={<Product/>}/>
    <Route path="/publicar" element={<Protected><Publish/></Protected>}/>
    <Route path="/painel" element={<Protected><Dashboard/></Protected>}/>
    <Route path="/meus-anuncios" element={<Protected><MyAds/></Protected>}/>
    <Route path="/favoritos" element={<Protected><Favorites/></Protected>}/>
    <Route path="/mensagens" element={<Protected><Chat/></Protected>}/>
    <Route path="/destaque/:id" element={<Protected><Boost/></Protected>}/>
    <Route path="/admin" element={<AdminOnly><Admin/></AdminOnly>}/>
    <Route path="/entrar" element={<Auth/>}/>
  </Routes></main><BottomNav/></div>
}
