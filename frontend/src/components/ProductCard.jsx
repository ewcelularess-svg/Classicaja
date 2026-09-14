import React, {useState} from 'react';
import {BadgeCheck, Heart, ImageOff, MapPin, Star} from 'lucide-react';
import {Link, useNavigate} from 'react-router-dom';
import {api, imageUrl} from '../lib/api';
import {useAuth} from '../main';

const money=(v)=>Number(v).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});

export default function ProductCard({p}){
  const {user}=useAuth();
  const nav=useNavigate();
  const [favorite,setFavorite]=useState(Boolean(p.favorite));
  const [busy,setBusy]=useState(false);

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

  return <article className="product-card product-card-premium">
    <Link to={`/produto/${p.id}`} className="product-card-link" aria-label={`Ver anúncio ${p.title}`}>
      <div className="product-image product-image-fit">
        {p.image_url
          ? <img src={imageUrl(p.image_url)} alt={p.title} loading="lazy"/>
          : <div className="placeholder"><ImageOff/><span>Sem foto</span></div>}

        <div className="card-badges">
          {p.condition&&<span className="condition-badge">{p.condition}</span>}
          {p.featured_active&&<span className="badge featured-badge"><Star size={12} fill="currentColor"/> Destaque</span>}
        </div>
      </div>

      <div className="product-body">
        <div className="price-block">
          <span className="price-label">Preço</span>
          <div className="price price-strong">{money(p.price)}</div>
        </div>
        <div className="title">{p.title}</div>
        <div className="meta"><MapPin size={14}/><span>{p.neighborhood?`${p.neighborhood}, `:''}{p.city} - {p.state}</span></div>
        <div className="card-footer">
          {p.seller?.verified
            ? <div className="verified-mini"><BadgeCheck size={14}/> Vendedor verificado</div>
            : <span className="local-sale">Anúncio local</span>}
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
