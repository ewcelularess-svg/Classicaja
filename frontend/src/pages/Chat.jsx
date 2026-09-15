import React,{useEffect,useMemo,useState} from 'react';
import {ArrowLeft,BadgeCheck,ExternalLink,MessageCircle,Search,Send,Trash2} from 'lucide-react';
import {Link,useSearchParams} from 'react-router-dom';
import {api,imageUrl} from '../lib/api';
import {useAuth} from '../main';

const when=(value)=>{
  if(!value) return '';
  try{
    const d=new Date(value);
    const today=new Date();
    const sameDay=d.toDateString()===today.toDateString();
    return sameDay?d.toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'}):d.toLocaleDateString('pt-BR',{day:'2-digit',month:'2-digit'});
  }catch{return ''}
};

export default function Chat(){
 const {user}=useAuth();
 const [params,setParams]=useSearchParams();
 const [convs,setConvs]=useState([]);
 const [messages,setMessages]=useState([]);
 const [text,setText]=useState('');
 const [filter,setFilter]=useState('');
 const [err,setErr]=useState('');
 const [sending,setSending]=useState(false);
 const [deleting,setDeleting]=useState('');
 const selected=params.get('c');

 const openConversation=(id)=>setParams({c:id});
 const backToList=()=>setParams({}, {replace:true});

 const loadConvs=()=>api('/api/me/conversations')
  .then(items=>{
    const rows=Array.isArray(items)?items:[];
    setConvs(rows);
    if(selected&&!rows.some(c=>c.id===selected)) backToList();
  })
  .catch(e=>setErr(e.message));

 const loadMessages=()=>selected
  ? api(`/api/conversations/${selected}/messages`)
      .then(data=>{
        setMessages(Array.isArray(data)?data:[]);
        window.dispatchEvent(new Event('classificaja:refresh-notifications'));
      })
      .catch(e=>setErr(e.message))
  : setMessages([]);

 useEffect(()=>{loadConvs()},[]);
 useEffect(()=>{loadMessages()},[selected]);
 useEffect(()=>{
   const timer=setInterval(()=>{
     loadConvs();
     if(selected) loadMessages();
   },5000);
   return()=>clearInterval(timer);
 },[selected]);

 const current=useMemo(()=>convs.find(c=>c.id===selected)||null,[convs,selected]);
 const filtered=useMemo(()=>{
   const q=filter.trim().toLowerCase();
   if(!q) return convs;
   return convs.filter(c=>`${c.other_user?.name||''} ${c.product?.title||''} ${c.last_message?.body||''}`.toLowerCase().includes(q));
 },[convs,filter]);

 const send=async e=>{
   e.preventDefault();
   const body=text.trim();
   if(!body||!selected||sending) return;
   try{
     setSending(true);
     await api(`/api/conversations/${selected}/messages`,{method:'POST',body:JSON.stringify({body})});
     setText('');
     await loadMessages();
     loadConvs();
   }catch(e){alert(e.message)}
   finally{setSending(false)}
 };

 const removeConversation=async(id)=>{
   const c=convs.find(x=>x.id===id);
   if(!window.confirm(`Excluir a conversa com ${c?.other_user?.name||'este usuário'} da sua lista?`)) return;
   try{
     setDeleting(id);
     await api(`/api/conversations/${id}`,{method:'DELETE'});
     setConvs(prev=>prev.filter(x=>x.id!==id));
     if(selected===id){backToList();setMessages([])}
   }catch(e){alert(e.message)}
   finally{setDeleting('')}
 };

 if(err) return <div className="page"><div className="empty"><h3>{err}</h3></div></div>;

 return <div className={`page chat-clean-page ${current?'chat-has-open':''}`}>
   <div className="chat-page-title">
     <span className="section-kicker">NEGOCIAÇÃO</span>
     <h1>Mensagens</h1>
   </div>

   <div className="chat-clean-shell">
     <aside className={`chat-clean-list ${current?'hide-on-mobile':''}`}>
       <div className="chat-clean-list-head">
         <div><b>Conversas</b><small>{convs.length} {convs.length===1?'conversa':'conversas'}</small></div>
         <div className="chat-clean-search"><Search/><input value={filter} onChange={e=>setFilter(e.target.value)} placeholder="Buscar conversa"/></div>
       </div>

       <div className="chat-clean-list-body">
         {filtered.length?filtered.map(c=><article className={`chat-conversation-row ${c.id===selected?'active':''}`} key={c.id}>
           <button className="chat-conversation-open" type="button" onClick={()=>openConversation(c.id)}>
             <span className="chat-conversation-thumb">{c.product?.image_url?<img src={imageUrl(c.product.image_url)} alt=""/>:<MessageCircle/>}</span>
             <span className="chat-conversation-copy">
               <span className="chat-conversation-top"><b>{c.other_user?.name||'Usuário'} {c.other_user?.verified&&<BadgeCheck/>}</b><time>{when(c.last_message?.created_at||c.updated_at)}</time></span>
               <small>{c.product?.title||'Anúncio'}</small>
               <em>{c.last_message?.body||'Toque para iniciar a conversa'}</em>
             </span>
             {c.unread>0&&<strong className="chat-unread">{c.unread}</strong>}
           </button>
           <button className="chat-row-delete" type="button" title="Excluir conversa" disabled={deleting===c.id} onClick={()=>removeConversation(c.id)}><Trash2/></button>
         </article>):<div className="chat-list-empty"><MessageCircle/><b>Nenhuma conversa</b><span>Quando alguém conversar sobre um anúncio, ela aparecerá aqui.</span></div>}
       </div>
     </aside>

     <section className={`chat-clean-panel ${current?'show-on-mobile':''}`}>
       {current?<>
         <header className="chat-clean-head">
           <button type="button" className="chat-clean-back" onClick={backToList}><ArrowLeft/></button>
           <span className="chat-clean-head-thumb">{current.product?.image_url?<img src={imageUrl(current.product.image_url)} alt=""/>:<MessageCircle/>}</span>
           <div className="chat-clean-head-copy"><b>{current.other_user?.name||'Usuário'}</b><small>{current.product?.title||'Anúncio'}</small></div>
           <div className="chat-clean-head-actions">
             {current.product?.id&&<Link title="Ver anúncio" to={`/produto/${current.product.id}`}><ExternalLink/></Link>}
             <button type="button" title="Excluir conversa" onClick={()=>removeConversation(current.id)}><Trash2/></button>
           </div>
         </header>

         <div className="chat-clean-messages">
           {messages.length?messages.map(m=><div key={m.id} className={`chat-bubble ${m.sender_id===user.id?'mine':'theirs'}`}><span>{m.body}</span><small>{new Date(m.created_at).toLocaleString('pt-BR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})}</small></div>):<div className="chat-message-empty"><MessageCircle/><span>Envie a primeira mensagem sobre este anúncio.</span></div>}
         </div>

         <form className="chat-clean-compose" onSubmit={send}>
           <input value={text} onChange={e=>setText(e.target.value)} placeholder="Digite sua mensagem..." maxLength={2000}/>
           <button type="submit" disabled={!text.trim()||sending}><Send/></button>
         </form>
       </>:<div className="chat-clean-placeholder"><MessageCircle/><b>Escolha uma conversa</b><span>Selecione uma conversa ao lado para começar.</span></div>}
     </section>
   </div>
 </div>
}
