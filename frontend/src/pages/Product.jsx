import React, {useEffect, useMemo, useState} from 'react';
import {ArrowLeft, BadgeCheck, ChevronLeft, ChevronRight, Flag, Heart, MapPin, MessageCircle, Pause, Pencil, Play, Share2, Star, Tag, X, ZoomIn} from 'lucide-react';
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
 const [activeIndex,setActiveIndex]=useState(0);
 const [related,setRelated]=useState([]);
 const [zoomOpen,setZoomOpen]=useState(false);
 const [autoPlay,setAutoPlay]=useState(true);
 const [hovering,setHovering]=useState(false);
 const {user}=useAuth();
 const nav=useNavigate();

 useEffect(()=>{
  setErr('');
  setP(null);
  setRelated([]);
  setActiveIndex(0);
  setZoomOpen(false);
  Promise.all([
    api(`/api/products/${id}`),
    api(`/api/products/${id}/related?limit=4`).catch(()=>[])
  ]).then(([product, rel])=>{
    setP(product);
    setRelated(rel||[]);
  }).catch(e=>setErr(e.message));
 },[id]);

 const images = useMemo(()=>((p?.images&&p.images.length?p.images:(p?.image_url?[p.image_url]:[]))||[]),[p]);
 const activeImage = images[activeIndex] || images[0] || '';

 useEffect(()=>{
   if(images.length<=1 || !autoPlay || hovering || zoomOpen) return;
   const timer=setInterval(()=>setActiveIndex(i=>(i+1)%images.length),4000);
   return ()=>clearInterval(timer);
 },[images.length,autoPlay,hovering,zoomOpen]);

 useEffect(()=>{
   if(activeIndex>=images.length && images.length) setActiveIndex(0);
 },[images.length,activeIndex]);

 if(err) return <div className="page narrow"><div className="empty"><h3>{err}</h3></div></div>;
 if(!p) return <div className="loading">Carregando anúncio...</div>;

 const phone=(p.seller?.phone||'').replace(/\D/g,'');
 const wa=phone?`https://wa.me/55${phone}?text=${encodeURIComponent(`Olá, vi seu anúncio "${p.title}" no ClassificaJá.`)}`:'#';
 const favorite=async()=>{try{const r=await api(`/api/products/${p.id}/favorite`,{method:'POST'});setP({...p,favorite:r.favorite})}catch{nav('/entrar')}};
 const chat=async()=>{try{const r=await api(`/api/products/${p.id}/conversation`,{method:'POST'});nav(`/mensagens?c=${r.conversation_id}`)}catch(e){if(!user)nav('/entrar');else alert(e.message)}};
 const share=()=>navigator.share?.({title:p.title,url:location.href})||navigator.clipboard?.writeText(location.href).then(()=>alert('Link copiado'));
 const report=async()=>{if(!user){nav('/entrar');return}const reason=prompt('Motivo da denúncia (fraude, item proibido, informação falsa...):');if(!reason)return;try{await api(`/api/products/${p.id}/report`,{method:'POST',body:JSON.stringify({reason,details:''})});alert('Denúncia enviada para moderação.')}catch(e){alert(e.message)}};
 const promoActive = Boolean(p.promo_active || (p.original_price && Number(p.original_price) > Number(p.price)));
 const prevImage=()=>setActiveIndex(i=>(i-1+Math.max(images.length,1))%Math.max(images.length,1));
 const nextImage=()=>setActiveIndex(i=>(i+1)%Math.max(images.length,1));

 return <div className="page product-page">
  <Link className="back" to="/"><ArrowLeft/> Voltar</Link>
  <div className="product-layout">
    <div className="product-gallery-wrap" onMouseEnter={()=>setHovering(true)} onMouseLeave={()=>setHovering(false)}>
      <div className="gallery gallery-main carousel-gallery">
        {activeImage?<img src={imageUrl(activeImage)} alt={p.title} onClick={()=>setZoomOpen(true)}/>:<div className="product-placeholder">📦</div>}
        {images.length>1 && <>
          <button type="button" className="carousel-arrow carousel-prev" onClick={prevImage} aria-label="Foto anterior"><ChevronLeft/></button>
          <button type="button" className="carousel-arrow carousel-next" onClick={nextImage} aria-label="Próxima foto"><ChevronRight/></button>
          <div className="carousel-counter">{activeIndex+1}/{images.length}</div>
          <button type="button" className="carousel-play" onClick={()=>setAutoPlay(v=>!v)} aria-label={autoPlay?'Pausar carrossel':'Ativar carrossel'}>{autoPlay?<Pause size={16}/>:<Play size={16}/>}</button>
        </>}
        {activeImage && <button type="button" className="zoom-button" onClick={()=>setZoomOpen(true)}><ZoomIn size={17}/> Ampliar</button>}
      </div>
      {images.length>1 && <div className="gallery-thumbs">{images.map((img,i)=><button type="button" key={img+i} className={`gallery-thumb ${activeIndex===i?'active':''}`} onClick={()=>setActiveIndex(i)}><img src={imageUrl(img)} alt={`Foto ${i+1}`}/></button>)}</div>}
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
      <div className={`payment-mode-detail ${p.payment_mode==='installments'?'parcelado':'avista'}`}>{p.payment_mode==='installments'?'Aceita parcelamento — condições definidas pelo banco no checkout':'Venda à vista'}</div>
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
        <h2>Mais anúncios parecidos perto de você</h2>
        <p className="related-subtitle">Selecionados pela mesma categoria, cidade e faixa de preço próxima.</p>
      </div>
    </div>
    <div className="product-grid related-products-grid">
      {related.map(item=><ProductCard key={item.id} p={item}/>) }
    </div>
  </section>}

  {zoomOpen && activeImage && <div className="image-lightbox" role="dialog" aria-modal="true" aria-label="Imagem ampliada" onClick={()=>setZoomOpen(false)}>
    <button type="button" className="lightbox-close" onClick={()=>setZoomOpen(false)}><X/></button>
    {images.length>1 && <button type="button" className="lightbox-arrow lightbox-prev" onClick={(e)=>{e.stopPropagation();prevImage()}}><ChevronLeft/></button>}
    <div className="lightbox-image-wrap" onClick={e=>e.stopPropagation()}>
      <img src={imageUrl(activeImage)} alt={p.title}/>
      <div className="lightbox-counter">{activeIndex+1} de {images.length}</div>
    </div>
    {images.length>1 && <button type="button" className="lightbox-arrow lightbox-next" onClick={(e)=>{e.stopPropagation();nextImage()}}><ChevronRight/></button>}
  </div>}
 </div>
}
