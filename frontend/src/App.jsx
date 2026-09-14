import React from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import Header from './components/Header';
import BottomNav from './components/BottomNav';
import Home from './pages/Home';
import Product from './pages/Product';
import Publish from './pages/Publish';
import EditProduct from './pages/EditProduct';
import Auth from './pages/Auth';
import MyAds from './pages/MyAds';
import Favorites from './pages/Favorites';
import Dashboard from './pages/Dashboard';
import Chat from './pages/Chat';
import Boost from './pages/Boost';
import Admin from './pages/Admin';
import PlanChoice from './pages/PlanChoice';
import { useAuth } from './main';
import { api } from './lib/api';

function Protected({children}) {
  const {user, loading} = useAuth();
  if (loading) return <div className="loading">Carregando...</div>;
  return user ? children : <Navigate to="/entrar" />;
}
function AdminOnly({children}) {
  const {user, loading} = useAuth();
  if (loading) return <div className="loading">Carregando...</div>;
  if (!user) return <Navigate to="/entrar" />;
  if (user.role !== 'admin') {
    return <div className="page master-access-denied">
      <div className="master-access-card">
        <div className="master-access-icon">🔐</div>
        <span className="section-kicker">PAINEL MASTER</span>
        <h1>Acesso administrativo restrito</h1>
        <p>Esta conta está conectada, mas ainda não possui permissão de administrador.</p>
        <p className="master-access-email">Conta atual: <b>{user.email}</b></p>
        <NavigateFallback/>
      </div>
    </div>;
  }
  return children;
}

function NavigateFallback(){
  return <div className="master-access-actions">
    <a className="secondary-btn" href="/">Voltar ao site</a>
    <a className="primary" href="/entrar">Entrar com outra conta</a>
  </div>;
}
function PublishGate(){
  const [state,setState]=React.useState({loading:true,ready:false});
  React.useEffect(()=>{
    let active=true;
    api('/api/me/publish-plan')
      .then(data=>{if(active)setState({loading:false,ready:Boolean(data?.ready)})})
      .catch(()=>{if(active)setState({loading:false,ready:false})});
    return()=>{active=false};
  },[]);
  if(state.loading) return <div className="loading">Verificando plano...</div>;
  return state.ready ? <Publish/> : <Navigate to="/escolher-plano" replace/>;
}
export default function App(){
  return <div className="app"><Header/><main><Routes>
    <Route path="/" element={<Home/>}/>
    <Route path="/produto/:id" element={<Product/>}/>
    <Route path="/escolher-plano" element={<Protected><PlanChoice/></Protected>}/>
    <Route path="/publicar" element={<Protected><PublishGate/></Protected>}/>
    <Route path="/editar/:id" element={<Protected><EditProduct/></Protected>}/>
    <Route path="/painel" element={<Protected><Dashboard/></Protected>}/>
    <Route path="/meus-anuncios" element={<Protected><MyAds/></Protected>}/>
    <Route path="/favoritos" element={<Protected><Favorites/></Protected>}/>
    <Route path="/mensagens" element={<Protected><Chat/></Protected>}/>
    <Route path="/destaque/:id" element={<Protected><Boost/></Protected>}/>
    <Route path="/admin" element={<AdminOnly><Admin/></AdminOnly>}/>
    <Route path="/entrar" element={<Auth/>}/>
  </Routes></main><BottomNav/></div>
}
