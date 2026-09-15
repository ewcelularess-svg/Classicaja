import React from 'react';
import {Home, LayoutDashboard, MessageCircle, PlusCircle, ShieldCheck, UserCircle} from 'lucide-react';
import {NavLink} from 'react-router-dom';
import {useAuth} from '../main';

export default function BottomNav(){
 const {user}=useAuth();
 return <nav className="bottom-nav">
  <NavLink to="/"><Home/><span>Início</span></NavLink>
  {user?.role==='admin'
    ? <NavLink to="/admin"><ShieldCheck/><span>Master</span></NavLink>
    : <NavLink to="/painel"><LayoutDashboard/><span>Painel</span></NavLink>}
  <NavLink className="sell" to={user?'/escolher-plano':'/entrar'}><PlusCircle/><span>Anunciar</span></NavLink>
  <NavLink to="/mensagens"><MessageCircle/><span>Chat</span></NavLink>
  <NavLink to="/meus-anuncios"><UserCircle/><span>Anúncios</span></NavLink>
 </nav>
}
