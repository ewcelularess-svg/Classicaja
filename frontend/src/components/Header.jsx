import React from 'react';
import {Heart, LayoutDashboard, LogOut, MessageCircle, PlusCircle, Search, ShieldCheck, UserCircle} from 'lucide-react';
import {Link, NavLink, useNavigate} from 'react-router-dom';
import {useAuth} from '../main';
export default function Header(){
 const {user, logout}=useAuth(); const nav=useNavigate();
 return <header className="topbar"><div className="topbar-inner">
  <Link className="brand" to="/"><span className="brand-mark">C</span><span>ClassificaJá</span></Link>
  <nav className="desktop-nav"><NavLink to="/">Comprar</NavLink><a href="/#produtos">Produtos</a><a href="/#categorias">Categorias</a>{user&&<NavLink to="/painel">Meu painel</NavLink>}</nav>
  <div className="header-actions"><Link title="Buscar" to="/"><Search/></Link>{user&&<Link title="Mensagens" to="/mensagens"><MessageCircle/></Link>}<Link title="Favoritos" to="/favoritos"><Heart/></Link>
   {user ? <><Link className="publish-mini" to="/publicar"><PlusCircle/> Anunciar</Link>{user.role==='admin'&&<Link title="Administração" to="/admin"><ShieldCheck/></Link>}<button className="icon-btn" title="Sair" onClick={()=>{logout();nav('/')}}><LogOut/></button></> : <Link className="login-link" to="/entrar"><UserCircle/> Entrar</Link>}
  </div>
 </div></header>
}
