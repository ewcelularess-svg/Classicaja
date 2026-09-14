import React, {useEffect, useMemo, useState} from 'react';
import {ChevronRight, MapPin, Search, ShieldCheck, Sparkles, Tag} from 'lucide-react';
import {api} from '../lib/api';
import ProductCard from '../components/ProductCard';

export default function Home(){
 const [products,setProducts]=useState([]); const [categories,setCategories]=useState([]); const [stats,setStats]=useState({products:0,sellers:0,cities:0});
 const [q,setQ]=useState(''); const [cat,setCat]=useState(''); const [sort,setSort]=useState('newest'); const [city,setCity]=useState(''); const [neighborhood,setNeighborhood]=useState('');
 const load=()=>api(`/api/products?search=${encodeURIComponent(q)}&category=${encodeURIComponent(cat)}&city=${encodeURIComponent(city)}&neighborhood=${encodeURIComponent(neighborhood)}&sort=${sort}`).then(setProducts).catch(()=>setProducts([]));
 useEffect(()=>{api('/api/categories').then(setCategories); api('/api/public/stats').then(setStats).catch(()=>{}); load()},[]);
 useEffect(()=>{const t=setTimeout(load,250); return ()=>clearTimeout(t)},[q,cat,sort,city,neighborhood]);
 const featured=useMemo(()=>products.filter(p=>p.featured_active).slice(0,4),[products]);
 return <>
  <section className="hero"><div className="hero-copy"><span className="eyebrow">COMPRE E VENDA PERTO DE VOCÊ</span><h1>Seu marketplace local, simples e direto.</h1><p>Publique produtos, converse com compradores e negocie de forma organizada em um só lugar.</p>
   <div className="search-box"><Search/><input value={q} onChange={e=>setQ(e.target.value)} placeholder="O que você está procurando?"/><button onClick={load}>Buscar</button></div>
   <div className="location-filters"><label><MapPin/><input value={city} onChange={e=>setCity(e.target.value)} placeholder="Cidade"/></label><label><input value={neighborhood} onChange={e=>setNeighborhood(e.target.value)} placeholder="Bairro"/></label></div>
   <div className="trust-row"><span><ShieldCheck/> vendedores verificados</span><span><Tag/> venda direta</span><span><Sparkles/> anúncios em destaque</span></div>
   <div className="hero-stats"><div><b>{stats.products}</b><span>anúncios</span></div><div><b>{stats.sellers}</b><span>usuários</span></div><div><b>{stats.cities}</b><span>cidades</span></div></div>
  </div><div className="hero-panel"><div className="hero-card big">🚗<b>Veículos</b><span>Carros, motos e peças</span></div><div className="hero-stack"><div className="hero-card">📱<b>Celulares</b></div><div className="hero-card">🏠<b>Imóveis</b></div></div></div></section>

  <section className="section" id="categorias"><div className="section-head"><div><span className="section-kicker">EXPLORE</span><h2>Categorias</h2></div><button className="text-btn" onClick={()=>setCat('')}>Ver todas <ChevronRight/></button></div>
   <div className="category-grid">{categories.map(c=><button key={c.slug} className={`category-card ${cat===c.slug?'active':''}`} onClick={()=>setCat(cat===c.slug?'':c.slug)}><span>{c.icon}</span><b>{c.name}</b></button>)}</div>
  </section>

  {featured.length>0 && <section className="section dark-section"><div className="section-head light"><div><span className="section-kicker">PATROCINADOS</span><h2>Anúncios em destaque</h2></div></div><div className="horizontal-cards">{featured.map(p=><ProductCard key={p.id} p={p}/>)}</div></section>}

  <section className="section" id="produtos"><div className="section-head"><div><span className="section-kicker">CLASSIFICADOS</span><h2>Produtos</h2></div><select value={sort} onChange={e=>setSort(e.target.value)}><option value="newest">Mais recentes</option><option value="price_low">Menor preço</option><option value="price_high">Maior preço</option><option value="popular">Mais vistos</option></select></div>
   {products.length ? <div className="product-grid">{products.map(p=><ProductCard key={p.id} p={p}/>)}</div> : <div className="empty"><div>🛍️</div><h3>Nenhum anúncio encontrado</h3><p>Altere os filtros ou publique o primeiro anúncio nesta região.</p></div>}
  </section>
 </>
}
