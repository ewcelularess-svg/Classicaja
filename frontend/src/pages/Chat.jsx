import React,{useEffect,useMemo,useState} from 'react';
import {ArrowLeft, BadgeCheck, ExternalLink, MessageCircle, Send, Trash2} from 'lucide-react';
import {Link, useSearchParams} from 'react-router-dom';
import {api,imageUrl} from '../lib/api';
import {useAuth} from '../main';

function formatTime(value){
  if(!value) return '';
  try{return new Date(value).toLocaleString('pt-BR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});}catch{return '';}
}

export default function Chat(){
 const {user}=useAuth();
 const [params,setParams]=useSearchParams();
 const [convs,setConvs]=useState([]);
 const [messages,setMessages]=useState([]);
 const [text,setText]=useState('');
 const [err,setErr]=useState('');
 const [busy,setBusy]=useState(false);
 const [deletingId,setDeletingId]=useState('');
 const selected=params.get('c');

 const openConversation=(id)=>setParams({c:id});
 const clearConversation=()=>setParams({}, {replace:true});

 const loadConvs=()=>api('/api/me/conversations')
  .then(items=>{
    setConvs(items);
    if(selected && !items.some(c=>c.id===selected)){
      clearConversation();
    }
  })
  .catch(e=>setErr(e.message));

 const loadMessages=()=>selected
  ? api(`/api/conversations/${selected}/messages`)
      .then(data=>{setMessages(data);window.dispatchEvent(new Event('classificaja:refresh-notifications'));})
      .catch(e=>setErr(e.message))
  : setMessages([]);

 useEffect(()=>{loadConvs();},[]);
 useEffect(()=>{loadMessages();},[selected]);
 useEffect(()=>{
   const timer=setInterval(()=>{
     loadConvs();
     if(selected) loadMessages();
   },5000);
   return()=>clearInterval(timer);
 },[selected]);

 const current=useMemo(()=>convs.find(c=>c.id===selected),[convs,selected]);

 const send=async e=>{
   e.preventDefault();
   if(!text.trim()||!selected||busy)return;
   try{
    setBusy(true);
    await api(`/api/conversations/${selected}/messages`,{method:'POST',body:JSON.stringify({body:text})});
    setText('');
    await loadMessages();
    loadConvs();
   }catch(e){setErr(e.message)}
   finally{setBusy(false)}
 };

 const removeConversation=async (id)=>{
   const conv=convs.find(c=>c.id===id);
   const name=conv?.other_user?.name||'esta conversa';
   if(!window.confirm(`Deseja excluir ${name} da sua lista?`)) return;
   try{
     setDeletingId(id);
     await api(`/api/conversations/${id}`,{method:'DELETE'});
     const remaining=convs.filter(c=>c.id!==id);
     setConvs(remaining);
     if(selected===id){
       if(remaining[0]) setParams({c:remaining[0].id},{replace:true});
       else clearConversation();
       setMessages([]);
     }
   }catch(e){alert(e.message)}
   finally{setDeletingId('')}
 };

 if(err) return <div className="page"><div className="empty"><h3>{err}</h3></div></div>;
 return <div className="page chat-page-pro">
  <div className="section-head chat-section-head">
    <div><span className="section-kicker">NEGOCIAÇÃO</span><h1>Mensagens</h1><p className="section-subcopy">Escolha uma conversa, negocie com mais clareza e exclua conversas quando quiser.</p></div>
  </div>

  <div className={`chat-layout chat-layout-pro ${current?'has-current':''}`}>
    <aside className={`conversation-list conversation-list-pro ${current?'mobile-hidden':''}`}>
      <div className="conversation-topbar">
        <div>
          <b>Conversas</b>
          <small>{convs.length ? `${convs.length} conversa${convs.length>1?'s':''}` : 'Sem conversas no momento'}</small>
        </div>
      </div>

      {convs.length ? convs.map(c=>{
        const active=c.id===selected;
        return <article className={`conversation-card ${active?'selected':''}`} key={c.id}>
          <button type="button" className="conversation-main" onClick={()=>openConversation(c.id)}>
            <span className="conv-thumb">{c.product?.image_url?<img src={imageUrl(c.product.image_url)}/>:<MessageCircle/>}</span>
            <span className="conv-copy">
              <b>{c.other_user?.name} {c.other_user?.verified&&<BadgeCheck/>}</b>
              <small>{c.product?.title || 'Anúncio removido'}</small>
              <em>{c.last_message?.body||'Conversa iniciada'}</em>
            </span>
            <span className="conv-side">
              <small>{formatTime(c.last_message?.created_at || c.updated_at)}</small>
              {c.unread>0&&<strong>{c.unread}</strong>}
            </span>
          </button>
          <div className="conversation-actions">
            <button type="button" className="chat-mini-btn primary" onClick={()=>openConversation(c.id)}><MessageCircle/> Conversar</button>
            <button type="button" className="chat-mini-btn danger" disabled={deletingId===c.id} onClick={()=>removeConversation(c.id)}><Trash2/> Excluir</button>
          </div>
        </article>
      }):<div className="empty compact"><h3>Nenhuma conversa ainda.</h3><p>Abra um anúncio e toque em “Conversar no chat”.</p></div>}
    </aside>

    <section className={`message-panel message-panel-pro ${current?'mobile-show':''}`}>
      {current ? <>
        <div className="message-head message-head-pro">
          <div className="message-head-main">
            <button type="button" className="chat-back-btn" onClick={clearConversation}><ArrowLeft/></button>
            <span className="conv-thumb small">{current.product?.image_url?<img src={imageUrl(current.product.image_url)}/>:<MessageCircle/>}</span>
            <div>
              <b>{current.other_user?.name}</b>
              <small>{current.product?.title}</small>
            </div>
          </div>
          <div className="message-head-actions">
            {current.product?.id && <Link className="chat-head-link" to={`/produto/${current.product.id}`}><ExternalLink/> Ver anúncio</Link>}
            <button type="button" className="chat-head-link danger" onClick={()=>removeConversation(current.id)}><Trash2/> Excluir</button>
          </div>
        </div>

        <div className="message-scroll message-scroll-pro">
          {messages.length ? messages.map(m=><div key={m.id} className={`bubble ${m.sender_id===user.id?'mine':'theirs'}`}>
            <span>{m.body}</span>
            <small>{new Date(m.created_at).toLocaleString('pt-BR')}</small>
          </div>) : <div className="chat-empty">Envie a primeira mensagem sobre este produto.</div>}
        </div>

        <form className="message-form message-form-pro" onSubmit={send}>
          <input value={text} onChange={e=>setText(e.target.value)} placeholder="Digite sua mensagem..." maxLength={2000}/>
          <button disabled={busy || !text.trim()}><Send/></button>
        </form>
      </> : <div className="chat-empty center pro"><MessageCircle/><b>Escolha uma conversa</b><span>Selecione um contato na lateral para começar a negociar.</span></div>}
    </section>
  </div>
 </div>
}
