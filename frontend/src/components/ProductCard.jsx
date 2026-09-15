import React, {useState} from 'react';
import {BadgeCheck, Heart, ImageOff, MapPin, Star, Tag, Clock3} from 'lucide-react';
import {Link, useNavigate} from 'react-router-dom';
import {api, imageUrl} from '../lib/api';
import {useAuth} from '../main';

const money=(v)=>Number(v).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});

export default function ProductCard({p}){
  const {user}=useAuth();
  const nav=useNavigate();
  const [favorite,setFavorite]=useState(Boolean(p.favorite));
  const [busy,setBusy]=useState(false);
  const promoActive = Boolean(p.promo_active || (p.original_price && Number(p.original_price) > Number(p.price)));
  const mainImage = (p.images && p.images[0]) || p.image_url;
  const isRecent = (()=>{ try{return Date.now()-new Date(p.created_at).getTime() < 24*60*60*1000}catch{return false} })();
  const compactLocation = [p.neighborhood, p.city, p.state].filter(Boolean).join(', ').replace(', ', ' • ');
  const showCondition = p.condition && !String(p.condition).toLowerCase().includes('novo');

  async function toggleFavorite(e){
    e.preventDefault();
    e.stopPropagation();
    if(!user){ nav('/entrar'); return; }
    if(user.id===p.seller_id) return;
    if(busy) return;
    setBusy(true);
    try{
      const r=await api(`/api/products/${p.id}/favorite`,{method:'POST'});
      setFavorite(Boolean(r.favorite));
    }catch(err){
      console.error(err);
    }finally{
      setBusy(false);
    }
  }

  return <article className="product-card product-card-premium product-card-clean">
    <Link to={`/produto/${p.id}`} className="product-card-link" aria-label={`Ver anúncio ${p.title}`}>
      <div className="product-image product-image-fit">
        {mainImage
          ? <img src={imageUrl(mainImage)} alt={p.title} loading="lazy"/>
          : <div className="placeholder"><ImageOff/><span>Sem foto</span></div>}

      </div>

      <div className="product-body">
        <div className="price-block">
          {promoActive && p.original_price ? <div className="old-price">de {money(p.original_price)}</div> : null}
          <div className="price price-strong">{money(p.price)}</div>
        </div>
        <div className="title">{p.title}</div>
        {(p.featured_active || promoActive || isRecent || showCondition || (p.images && p.images.length > 1)) && <div className="card-info-chips">
          {p.featured_active&&<span className="card-info-chip featured"><Star size={11} fill="currentColor"/> Destaque</span>}
          {promoActive&&<span className="card-info-chip promo"><Tag size={11}/> Promoção</span>}
          {isRecent&&<span className="card-info-chip recent"><Clock3 size={11}/> Recente</span>}
          {showCondition&&<span className="card-info-chip condition">{p.condition}</span>}
          {p.images && p.images.length > 1 && <span className="card-info-chip photos">{p.images.length} fotos</span>}
        </div>}
        <div className="clean-meta-stack">
          <div className="meta clean-meta"><MapPin size={14}/><span>{compactLocation || `${p.city||''}${p.state?` - ${p.state}`:''}`}</span></div>
          {p.seller?.verified
            ? <div className="verified-mini verified-inline"><BadgeCheck size={14}/> Vendedor verificado</div>
            : <span className="local-sale local-inline">Anúncio local</span>}
        </div>
      </div>
    </Link>

    {user?.id!==p.seller_id&&<button
      type="button"
      className={`heart ${favorite?'active':''}`}
      onClick={toggleFavorite}
      disabled={busy}
      aria-label={favorite?'Remover dos favoritos':'Adicionar aos favoritos'}
      title={favorite?'Remover dos favoritos':'Adicionar aos favoritos'}
    >
      <Heart size={18} fill={favorite?'currentColor':'none'}/>
    </button>}
  </article>
}
