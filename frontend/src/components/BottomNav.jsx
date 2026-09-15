import React from 'react';
import {Home, LayoutDashboard, MessageCircle, PlusCircle, UserCircle} from 'lucide-react';
import {NavLink} from 'react-router-dom';
import {useAuth} from '../main';

export default function BottomNav(){
 const {user}=useAuth();
 return <nav className="bottom-nav">
  <NavLink to="/"><Home/><span>Início</span></NavLink>
  <NavLink to={user?'/painel':'/entrar'}><LayoutDashboard/><span>Painel</span></NavLink>
  <NavLink className="sell" to={user?'/publicar':'/entrar'}><PlusCircle/><span>Anunciar</span></NavLink>
  <NavLink to="/mensagens"><MessageCircle/><span>Chat</span></NavLink>
  <NavLink to="/meus-anuncios"><UserCircle/><span>Anúncios</span></NavLink>
 </nav>
}
