import React, {useEffect, useMemo, useState} from 'react';
import {ArrowLeft, BadgeCheck, Flag, Heart, MapPin, MessageCircle, Pencil, Share2, Star, Tag} from 'lucide-react';
import {Link, useNavigate, useParams} from 'react-router-dom';
import {api, imageUrl} from '../lib/api';
import {useAuth} from '../main';
import ProductCard from '../components/ProductCard';

const money=v=>Number(v).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
const statusLabel=s=>({active:'Ativo',paused:'Pausado',rejected:'Rejeitado',sold:'Vendido'}[s]||s);

export default function Product(){
 const {id}=useParams();
 const [p,setP]=useState(null);
 const [err,setErr]=useState('');
 const [activeImage,setActiveImage]=useState('');
 const [related,setRelated]=useState([]);
 const {user}=useAuth();
 const nav=useNavigate();

 useEffect(()=>{
  api(`/api/products/${id}`)
   .then((data)=>{
     setP(data);
     const first=((data.images&&data.images[0])||data.image_url||'');
     setActiveImage(first);
   })
   .catch(e=>setErr(e.message));
 },[id]);

 useEffect(()=>{
   if(!p) return;
   api(`/api/products?category=${encodeURIComponent(p.category_slug||'')}&city=${encodeURIComponent(p.city||'')}&sort=popular&limit=8`)
     .then((items)=>setRelated((items||[]).filter(item=>item.id!==p.id).slice(0,4)))
     .catch(()=>setRelated([]));
 },[p]);

 const images = useMemo(()=>((p?.images&&p.images.length?p.images:(p?.image_url?[p.image_url]:[]))||[]),[p]);
 if(err) return <div className="page narrow"><div className="empty"><h3>{err}</h3></div></div>;
 if(!p) return <div className="loading">Carregando anúncio...</div>;
 const phone=(p.seller?.phone||'').replace(/\D/g,'');
 const wa=phone?`https://wa.me/55${phone}?text=${encodeURIComponent(`Olá, vi seu anúncio "${p.title}" no ClassificaJá.`)}`:'#';
 const favorite=async()=>{try{const r=await api(`/api/products/${p.id}/favorite`,{method:'POST'});setP({...p,favorite:r.favorite})}catch{nav('/entrar')}};
 const chat=async()=>{try{const r=await api(`/api/products/${p.id}/conversation`,{method:'POST'});nav(`/mensagens?c=${r.conversation_id}`)}catch(e){if(!user)nav('/entrar');else alert(e.message)}};
 const share=()=>navigator.share?.({title:p.title,url:location.href})||navigator.clipboard?.writeText(location.href).then(()=>alert('Link copiado'));
 const report=async()=>{if(!user){nav('/entrar');return}const reason=prompt('Motivo da denúncia (fraude, item proibido, informação falsa...):');if(!reason)return;try{await api(`/api/products/${p.id}/report`,{method:'POST',body:JSON.stringify({reason,details:''})});alert('Denúncia enviada para moderação.')}catch(e){alert(e.message)}};
 const installment = p.installments && p.installments.amount ? p.installments : null;
 const promoActive = Boolean(p.promo_active || (p.original_price && Number(p.original_price) > Number(p.price)));

 return <div className="page product-page">
  <Link className="back" to="/"><ArrowLeft/> Voltar</Link>
  <div className="product-layout">
    <div className="product-gallery-wrap">
      <div className="gallery gallery-main">{activeImage?<img src={imageUrl(activeImage)} alt={p.title}/>:<div className="product-placeholder">📦</div>}</div>
      {images.length>1 && <div className="gallery-thumbs">{images.map((img,i)=><button type="button" key={img+i} className={`gallery-thumb ${activeImage===img?'active':''}`} onClick={()=>setActiveImage(img)}><img src={imageUrl(img)} alt={`Foto ${i+1}`}/></button>)}</div>}
    </div>

    <aside className="product-info">
      <div className="product-top-actions">
        <div className="pill-row">
          <span className="pill">{p.condition}</span>
          {p.featured_active&&<span className="pill gold"><Star size={13}/> Destaque</span>}
          {promoActive&&<span className="pill promo-pill"><Tag size={13}/> Promoção</span>}
        </div>
        <div><button onClick={share}><Share2/></button><button className={p.favorite?'fav-on':''} onClick={favorite}><Heart/></button></div>
      </div>
      <h1>{p.title}</h1>
      {promoActive && p.original_price ? <div className="detail-old-price">de {money(p.original_price)}</div> : null}
      <div className="detail-price">{money(p.price)}</div>
      {installment && <div className="detail-installment">Parcelamento: em até {installment.count}x de {money(installment.amount)}</div>}
      <div className="location"><MapPin/> {p.neighborhood?`${p.neighborhood}, `:''}{p.city} - {p.state}</div>
      {user?.id===p.seller_id&&<Link className="edit-product-btn" to={`/editar/${p.id}`}><Pencil/> Editar anúncio</Link>}
      {user?.id!==p.seller_id&&<button className="chat-primary" onClick={chat}><MessageCircle/> Conversar no chat</button>}
      <a className={`whatsapp ${!phone?'disabled':''}`} target="_blank" rel="noreferrer" href={wa}><MessageCircle/> Falar pelo WhatsApp</a>
      <div className="seller-box"><span>Vendido por</span><b className="seller-name">{p.seller?.name || 'Vendedor'} {p.seller?.verified&&<BadgeCheck className="verified-icon"/>}</b>{p.seller?.verified&&<small>Identidade verificada pela plataforma</small>}</div>
      {user?.id!==p.seller_id&&<button className="report-btn" onClick={report}><Flag/> Denunciar anúncio</button>}
    </aside>
  </div>

  <section className="description">
    <h2>Descrição</h2>
    <p>{p.description}</p>
    <div className="facts"><span>Categoria: <b>{p.category_slug}</b></span><span>Visualizações: <b>{p.views}</b></span><span>Status: <b>{statusLabel(p.status)}</b></span><span>Fotos: <b>{images.length}</b></span></div>
  </section>

  {related.length>0 && <section className="related-products-section">
    <div className="section-head related-head">
      <div>
        <span className="section-kicker">ANÚNCIOS RELACIONADOS</span>
        <h2>Mais anúncios que podem interessar</h2>
      </div>
    </div>
    <div className="product-grid related-products-grid">
      {related.map(item=><ProductCard key={item.id} p={item}/>) }
    </div>
  </section>}
 </div>
}
