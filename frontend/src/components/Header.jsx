import React, {useEffect, useState} from 'react';
import {
  ChevronLeft,
  ChevronRight,
  Heart,
  LogOut,
  MapPin,
  MessageCircle,
  Plus,
  Search,
  ShieldCheck,
  UserCircle
} from 'lucide-react';
import {Link, NavLink, useLocation, useNavigate} from 'react-router-dom';
import {useAuth} from '../main';
import {api, imageUrl} from '../lib/api';
import NotificationsMenu from './NotificationsMenu';

export default function Header(){
  const {user, logout}=useAuth();
  const nav=useNavigate();
  const location=useLocation();
  const isHome=location.pathname==='/' ;
  const isProduct=location.pathname.startsWith('/produto/');
  const [term,setTerm]=useState('');
  const [city,setCity]=useState('');
  const [slides,setSlides]=useState([]);
  const [slideIndex,setSlideIndex]=useState(0);
  const [isSliderPaused,setIsSliderPaused]=useState(false);

  useEffect(()=>{
    if(!isHome){
      setSlides([]);
      setSlideIndex(0);
      return;
    }
    let active=true;
    api('/api/home-slides?limit=8')
      .then(data=>{if(active){setSlides(Array.isArray(data)?data:[]);setSlideIndex(0)}})
      .catch(()=>{if(active)setSlides([])});
    return()=>{active=false};
  },[isHome]);

  useEffect(()=>{
    if(!isHome||slides.length<2||isSliderPaused) return;
    const timer=setInterval(()=>setSlideIndex(i=>(i+1)%slides.length),8000);
    return()=>clearInterval(timer);
  },[isHome,slides.length,isSliderPaused]);

  function submitSearch(e){
    e.preventDefault();
    const params=new URLSearchParams();
    if(term.trim()) params.set('q',term.trim());
    if(city.trim()) params.set('city',city.trim());
    nav(`/${params.toString()?`?${params.toString()}`:''}`);
  }

  function moveSlide(step){
    if(!slides.length) return;
    setSlideIndex(i=>(i+step+slides.length)%slides.length);
  }

  const activeSlide=slides[slideIndex]||slides[0]||null;
  const activeImage=activeSlide?.image_url?imageUrl(activeSlide.image_url):null;
  const slideVisual=activeSlide&&activeImage?<>
    <span className="home-header-slide-accent accent-left" aria-hidden="true"/>
    <span className="home-header-slide-accent accent-right" aria-hidden="true"/>
    <span className="home-header-slide-badge">Destaque</span>
    <div className="home-header-slide-stage">
      <img className="home-header-slide-image" src={activeImage} alt={activeSlide.title||'Banner ClassificaJá'} loading="eager" decoding="async"/>
      <span className="home-header-slide-shine" aria-hidden="true"/>
    </div>
    {(activeSlide.title||activeSlide.subtitle)&&<span className="home-header-slide-caption">
      {activeSlide.title&&<strong>{activeSlide.title}</strong>}
      {activeSlide.subtitle&&<small>{activeSlide.subtitle}</small>}
    </span>}
  </>:null;

  return <header className={`topbar premium-topbar ${isHome?'home-topbar home-topbar-slider':''} ${isProduct?'product-topbar':''}`}>
    <div className={`topbar-inner premium-header-row ${isHome?'home-header-row':''}`}>
      <Link className="brand brand-premium" to="/" aria-label="ClassificaJá - Início">
        <img src="/logo-classificaja.png" alt="ClassificaJá" className="brand-logo"/>
      </Link>

      <form className={`header-search ${isHome?'header-home-search':''}`} onSubmit={submitSearch}>
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
          <Link className="publish-premium" to="/escolher-plano"><Plus/> <span>Anunciar</span></Link>
          {user.role==='admin'&&<Link className="header-action admin-header-action" title="Administração" to="/admin"><ShieldCheck/><span>Master</span></Link>}
          <button className="icon-btn logout-premium" title="Sair" onClick={()=>{logout();nav('/')}}><LogOut/></button>
        </> : <>
          <Link className="header-action login-premium" to="/entrar"><UserCircle/><span>Entrar</span></Link>
          <Link className="publish-premium" to="/entrar"><Plus/> <span>Anunciar</span></Link>
        </>}
      </div>
    </div>

    {isHome&&<div className="home-header-slider-shell" aria-label="Destaques do ClassificaJá">
      {activeSlide&&activeImage?<div className="home-header-slider" onMouseEnter={()=>setIsSliderPaused(true)} onMouseLeave={()=>setIsSliderPaused(false)} onTouchStart={()=>setIsSliderPaused(true)} onTouchEnd={()=>setIsSliderPaused(false)}>
        {activeSlide.target_url?<a className="home-header-slide" href={activeSlide.target_url} target="_blank" rel="noreferrer sponsored" aria-label={activeSlide.title||'Abrir destaque'}>{slideVisual}</a>:<div className="home-header-slide">{slideVisual}</div>}
        {slides.length>1&&<>
          <button type="button" className="home-header-slider-arrow prev" onClick={()=>moveSlide(-1)} aria-label="Banner anterior"><ChevronLeft/></button>
          <button type="button" className="home-header-slider-arrow next" onClick={()=>moveSlide(1)} aria-label="Próximo banner"><ChevronRight/></button>
          <div className="home-header-slider-dots" aria-label="Selecionar banner">
            {slides.map((item,index)=><button key={item.id} type="button" className={index===slideIndex?'active':''} onClick={()=>setSlideIndex(index)} aria-label={`Mostrar banner ${index+1}`}/>)}
          </div>
        </>}
      </div>:<div className="home-header-slider-empty">
        <strong>ClassificaJá</strong>
        <span>Cadastre banners em Master → Slider Home.</span>
      </div>}
    </div>}

    <div className="header-subnav">
      <div className={`header-subnav-inner ${isHome?'home-subnav-inner':''}`}>
        <NavLink to="/">Comprar</NavLink>
        <a href="/#produtos">Produtos</a>
        <a href="/#categorias">Categorias</a>
        {user&&<NavLink to="/meus-anuncios">Meus anúncios</NavLink>}
      </div>
    </div>
  </header>
}
