import React, {useEffect, useState} from 'react';
import {ArrowLeft, BadgeCheck, Flag, Heart, MapPin, MessageCircle, Share2, Star} from 'lucide-react';
import {Link, useNavigate, useParams} from 'react-router-dom';
import {api, imageUrl} from '../lib/api';
import {useAuth} from '../main';
const money=v=>Number(v).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
const statusLabel=s=>({active:'Ativo',paused:'Pausado',rejected:'Rejeitado',sold:'Vendido'}[s]||s);
export default function Product(){
 const {id}=useParams(); const [p,setP]=useState(null); const [err,setErr]=useState(''); const {user}=useAuth(); const nav=useNavigate();
 const load=()=>api(`/api/products/${id}`).then(setP).catch(e=>setErr(e.message));
 useEffect(()=>{load()},[id]);
 if(err) return <div className="page narrow"><div className="empty"><h3>{err}</h3></div></div>;
 if(!p) return <div className="loading">Carregando anúncio...</div>;
 const phone=(p.seller?.phone||'').replace(/\D/g,'');
 const wa=phone?`https://wa.me/55${phone}?text=${encodeURIComponent(`Olá, vi seu anúncio "${p.title}" no ClassificaJá.`)}`:'#';
 const favorite=async()=>{try{const r=await api(`/api/products/${p.id}/favorite`,{method:'POST'});setP({...p,favorite:r.favorite})}catch{nav('/entrar')}};
 const chat=async()=>{try{const r=await api(`/api/products/${p.id}/conversation`,{method:'POST'});nav(`/mensagens?c=${r.conversation_id}`)}catch(e){if(!user)nav('/entrar');else alert(e.message)}};
 const share=()=>navigator.share?.({title:p.title,url:location.href})||navigator.clipboard?.writeText(location.href).then(()=>alert('Link copiado'));
 const report=async()=>{if(!user){nav('/entrar');return}const reason=prompt('Motivo da denúncia (fraude, item proibido, informação falsa...):');if(!reason)return;try{await api(`/api/products/${p.id}/report`,{method:'POST',body:JSON.stringify({reason,details:''})});alert('Denúncia enviada para moderação.')}catch(e){alert(e.message)}};
 return <div className="page product-page"><Link className="back" to="/"><ArrowLeft/> Voltar</Link><div className="product-layout">
  <div className="gallery">{p.image_url?<img src={imageUrl(p.image_url)} alt={p.title}/>:<div className="product-placeholder">📦</div>}</div>
  <aside className="product-info"><div className="product-top-actions"><div className="pill-row"><span className="pill">{p.condition}</span>{p.featured_active&&<span className="pill gold"><Star size={13}/> Destaque</span>}</div><div><button onClick={share}><Share2/></button><button className={p.favorite?'fav-on':''} onClick={favorite}><Heart/></button></div></div>
   <h1>{p.title}</h1><div className="detail-price">{money(p.price)}</div><div className="location"><MapPin/> {p.neighborhood?`${p.neighborhood}, `:''}{p.city} - {p.state}</div>
   {user?.id!==p.seller_id&&<button className="chat-primary" onClick={chat}><MessageCircle/> Conversar no chat</button>}
   <a className={`whatsapp ${!phone?'disabled':''}`} target="_blank" rel="noreferrer" href={wa}><MessageCircle/> Falar pelo WhatsApp</a>
   <div className="seller-box"><span>Vendido por</span><b className="seller-name">{p.seller?.name || 'Vendedor'} {p.seller?.verified&&<BadgeCheck className="verified-icon"/>}</b>{p.seller?.verified&&<small>Identidade verificada pela plataforma</small>}</div>
   {user?.id!==p.seller_id&&<button className="report-btn" onClick={report}><Flag/> Denunciar anúncio</button>}
  </aside>
 </div><section className="description"><h2>Descrição</h2><p>{p.description}</p><div className="facts"><span>Categoria: <b>{p.category_slug}</b></span><span>Visualizações: <b>{p.views}</b></span><span>Status: <b>{statusLabel(p.status)}</b></span></div></section></div>
}
