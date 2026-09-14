import React,{useEffect,useState} from 'react';
import {api} from '../lib/api';
import ProductCard from '../components/ProductCard';
export default function Favorites(){const [items,setItems]=useState([]);const [err,setErr]=useState('');useEffect(()=>{api('/api/me/favorites').then(setItems).catch(e=>setErr(e.message))},[]);return <div className="page"><div className="section-head"><div><span className="section-kicker">SALVOS</span><h1>Favoritos</h1></div></div>{err?<div className="empty"><h3>{err}</h3></div>:items.length?<div className="product-grid">{items.map(p=><ProductCard key={p.id} p={p}/>)}</div>:<div className="empty"><h3>Nenhum favorito ainda.</h3><p>Salve anúncios para encontrar depois.</p></div>}</div>}
