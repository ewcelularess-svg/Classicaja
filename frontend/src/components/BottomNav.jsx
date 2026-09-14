import React from 'react';
import {Home, LayoutDashboard, MessageCircle, PlusCircle, UserCircle} from 'lucide-react';
import {NavLink} from 'react-router-dom';
export default function BottomNav(){return <nav className="bottom-nav">
 <NavLink to="/"><Home/><span>Início</span></NavLink><NavLink to="/painel"><LayoutDashboard/><span>Painel</span></NavLink><NavLink className="sell" to="/publicar"><PlusCircle/><span>Vender</span></NavLink><NavLink to="/mensagens"><MessageCircle/><span>Chat</span></NavLink><NavLink to="/meus-anuncios"><UserCircle/><span>Anúncios</span></NavLink>
</nav>}
