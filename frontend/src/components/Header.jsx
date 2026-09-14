import React, {useState} from 'react';
import {
  Heart,
  LogOut,
  MapPin,
  MessageCircle,
  Plus,
  Search,
  ShieldCheck,
  UserCircle
} from 'lucide-react';
import {Link, NavLink, useNavigate} from 'react-router-dom';
import {useAuth} from '../main';
import NotificationsMenu from './NotificationsMenu';

export default function Header(){
  const {user, logout}=useAuth();
  const nav=useNavigate();
  const [term,setTerm]=useState('');
  const [city,setCity]=useState('');

  function submitSearch(e){
    e.preventDefault();
    const params=new URLSearchParams();
    if(term.trim()) params.set('q',term.trim());
    if(city.trim()) params.set('city',city.trim());
    nav(`/${params.toString()?`?${params.toString()}`:''}`);
  }

  return <header className="topbar premium-topbar">
    <div className="topbar-inner premium-header-row">
      <Link className="brand brand-premium" to="/" aria-label="ClassificaJá - Início">
        <img src="/logo-classificaja.png" alt="ClassificaJá" className="brand-logo"/>
      </Link>

      <form className="header-search" onSubmit={submitSearch}>
        <div className="header-search-field header-search-keyword">
          <Search/>
          <input value={term} onChange={e=>setTerm(e.target.value)} placeholder="O que você está procurando?" aria-label="Buscar produtos"/>
        </div>
        <div className="header-search-divider"/>
        <div className="header-search-field header-search-city">
          <MapPin/>
          <input value={city} onChange={e=>setCity(e.target.value)} placeholder="Cidade" aria-label="Cidade"/>
        </div>
        <button type="submit">Buscar</button>
      </form>

      <div className="header-actions premium-actions">
        {user&&<NotificationsMenu/>}
        {user&&<Link className="header-action" title="Mensagens" to="/mensagens"><MessageCircle/><span>Mensagens</span></Link>}
        <Link className="header-action" title="Favoritos" to="/favoritos"><Heart/><span>Favoritos</span></Link>
        {user ? <>
          <Link className="header-action" title="Meu painel" to="/painel"><UserCircle/><span>Meu painel</span></Link>
          <Link className="publish-premium" to="/publicar"><Plus/> <span>Anunciar</span></Link>
          {user.role==='admin'&&<Link className="header-action admin-header-action" title="Administração" to="/admin"><ShieldCheck/><span>Master</span></Link>}
          <button className="icon-btn logout-premium" title="Sair" onClick={()=>{logout();nav('/')}}><LogOut/></button>
        </> : <>
          <Link className="header-action login-premium" to="/entrar"><UserCircle/><span>Entrar</span></Link>
          <Link className="publish-premium" to="/entrar"><Plus/> <span>Anunciar</span></Link>
        </>}
      </div>
    </div>

    <div className="header-subnav">
      <div className="header-subnav-inner">
        <NavLink to="/">Comprar</NavLink>
        <a href="/#produtos">Produtos</a>
        <a href="/#categorias">Categorias</a>
        {user&&<NavLink to="/meus-anuncios">Meus anúncios</NavLink>}
      </div>
    </div>
  </header>
}
