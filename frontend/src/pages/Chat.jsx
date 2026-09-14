import React,{useEffect,useMemo,useState} from 'react';
import {BadgeCheck, MessageCircle, Send} from 'lucide-react';
import {useSearchParams} from 'react-router-dom';
import {api,imageUrl} from '../lib/api';
import {useAuth} from '../main';

export default function Chat(){
 const {user}=useAuth(); const [params,setParams]=useSearchParams(); const [convs,setConvs]=useState([]); const [messages,setMessages]=useState([]); const [text,setText]=useState(''); const [err,setErr]=useState('');
 const selected=params.get('c');
 const loadConvs=()=>api('/api/me/conversations').then(items=>{setConvs(items); if(!selected&&items[0]) setParams({c:items[0].id},{replace:true})}).catch(e=>setErr(e.message));
 const loadMessages=()=>selected?api(`/api/conversations/${selected}/messages`).then(setMessages).catch(e=>setErr(e.message)):setMessages([]);
 useEffect(()=>{loadConvs()},[]); useEffect(()=>{loadMessages()},[selected]);
 const current=useMemo(()=>convs.find(c=>c.id===selected),[convs,selected]);
 const send=async e=>{e.preventDefault();if(!text.trim()||!selected)return;await api(`/api/conversations/${selected}/messages`,{method:'POST',body:JSON.stringify({body:text})});setText('');await loadMessages();loadConvs()};
 if(err) return <div className="page"><div className="empty"><h3>{err}</h3></div></div>;
 return <div className="page"><div className="section-head"><div><span className="section-kicker">NEGOCIAÇÃO</span><h1>Mensagens</h1></div></div>
  <div className="chat-layout"><aside className="conversation-list">{convs.length?convs.map(c=><button className={c.id===selected?'selected':''} key={c.id} onClick={()=>setParams({c:c.id})}><span className="conv-thumb">{c.product?.image_url?<img src={imageUrl(c.product.image_url)}/>:<MessageCircle/>}</span><span className="conv-copy"><b>{c.other_user?.name} {c.other_user?.verified&&<BadgeCheck/>}</b><small>{c.product?.title}</small><em>{c.last_message?.body||'Conversa iniciada'}</em></span>{c.unread>0&&<strong>{c.unread}</strong>}</button>):<div className="empty compact"><h3>Nenhuma conversa ainda.</h3><p>Abra um anúncio e toque em “Conversar no chat”.</p></div>}</aside>
   <section className="message-panel">{current?<><div className="message-head"><div><b>{current.other_user?.name}</b><small>{current.product?.title}</small></div></div><div className="message-scroll">{messages.length?messages.map(m=><div key={m.id} className={`bubble ${m.sender_id===user.id?'mine':'theirs'}`}><span>{m.body}</span><small>{new Date(m.created_at).toLocaleString('pt-BR')}</small></div>):<div className="chat-empty">Envie a primeira mensagem sobre este produto.</div>}</div><form className="message-form" onSubmit={send}><input value={text} onChange={e=>setText(e.target.value)} placeholder="Digite sua mensagem..."/><button><Send/></button></form></>:<div className="chat-empty center">Selecione uma conversa.</div>}</section>
  </div>
 </div>
}
