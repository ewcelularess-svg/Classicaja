import React,{useEffect,useState} from 'react';
import {Eye, Heart, MessageCircle, PackageCheck, PackageOpen, PlusCircle} from 'lucide-react';
import {Link} from 'react-router-dom';
import {api} from '../lib/api';

export default function Dashboard(){
 const [s,setS]=useState(null); const [err,setErr]=useState('');
 useEffect(()=>{api('/api/me/dashboard').then(setS).catch(e=>setErr(e.message))},[]);
 if(err) return <div className="page"><div className="empty"><h3>{err}</h3></div></div>;
 if(!s) return <div className="loading">Carregando painel...</div>;
 const cards=[
  ['Anúncios',s.total,<PackageOpen/>],['Ativos',s.active,<PackageCheck/>],['Visualizações',s.views,<Eye/>],['Favoritos recebidos',s.favorites_received,<Heart/>],['Mensagens não lidas',s.unread_messages,<MessageCircle/>]
 ];
 return <div className="page"><div className="section-head"><div><span className="section-kicker">ÁREA DO VENDEDOR</span><h1>Visão geral</h1></div><Link className="primary small" to="/publicar"><PlusCircle/> Novo anúncio</Link></div>
  <div className="metric-grid">{cards.map(([label,value,icon])=><div className="metric-card" key={label}><span className="metric-icon">{icon}</span><div><b>{value}</b><small>{label}</small></div></div>)}</div>
  <div className="dashboard-actions"><Link to="/meus-anuncios"><b>Gerenciar anúncios</b><span>Edite status, exclua ou coloque em destaque.</span></Link><Link to="/mensagens"><b>Abrir mensagens</b><span>Converse com compradores e vendedores.</span></Link><Link to="/favoritos"><b>Ver favoritos</b><span>Acesse os produtos que você salvou.</span></Link></div>
 </div>
}
