import React from 'react';
import {BadgeCheck, MapPin, Star} from 'lucide-react';
import {Link} from 'react-router-dom';
import {imageUrl} from '../lib/api';
const money=(v)=>Number(v).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
export default function ProductCard({p}){return <Link to={`/produto/${p.id}`} className="product-card">
 <div className="product-image">{p.image_url?<img src={imageUrl(p.image_url)} alt={p.title}/>:<div className="placeholder">📦</div>}{p.featured_active ? <span className="badge"><Star size={12}/> Destaque</span>:null}</div>
 <div className="product-body"><div className="price">{money(p.price)}</div><div className="title">{p.title}</div><div className="meta"><MapPin size={14}/>{p.neighborhood?`${p.neighborhood}, `:''}{p.city} - {p.state}</div>{p.seller?.verified&&<div className="verified-mini"><BadgeCheck size={14}/> Vendedor verificado</div>}</div>
 </Link>}
