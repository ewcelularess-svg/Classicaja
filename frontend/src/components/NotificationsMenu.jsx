import React,{useEffect,useRef,useState} from 'react';
import {Bell, CheckCheck, Megaphone} from 'lucide-react';
import {useNavigate} from 'react-router-dom';
import {api} from '../lib/api';

const recentEnough=(value)=>{
  try{return Date.now()-new Date(value).getTime() < 5*60*1000}catch{return false}
};

export default function NotificationsMenu(){
 const nav=useNavigate();
 const rootRef=useRef(null);
 const initialized=useRef(false);
 const lastNewest=useRef('');
 const [open,setOpen]=useState(false);
 const [items,setItems]=useState([]);
 const [unreadCount,setUnreadCount]=useState(0);
 const [toast,setToast]=useState(null);

 const refresh=async()=>{
  try{
   const [data,countData]=await Promise.all([api('/api/me/notifications?limit=20'),api('/api/me/notifications/unread-count')]);
   setItems(data||[]);
   setUnreadCount(Number(countData?.count||0));
   const newestUnread=(data||[]).find(n=>Boolean(n.unread));
   if(newestUnread){
    if(initialized.current && newestUnread.id!==lastNewest.current){
      setToast(newestUnread);
      setTimeout(()=>setToast(null),6500);
    }else if(!initialized.current && recentEnough(newestUnread.created_at)){
      setToast(newestUnread);
      setTimeout(()=>setToast(null),6500);
    }
    lastNewest.current=newestUnread.id;
   }
   initialized.current=true;
  }catch{}
 };

 useEffect(()=>{
  refresh();
  const timer=setInterval(refresh,20000);
  return()=>clearInterval(timer);
 },[]);

 useEffect(()=>{
  const close=(e)=>{if(rootRef.current&&!rootRef.current.contains(e.target)) setOpen(false)};
  document.addEventListener('mousedown',close);
  return()=>document.removeEventListener('mousedown',close);
 },[]);

 const unread=unreadCount;

 const openNotification=async(n)=>{
  if(n.unread){
   try{await api(`/api/me/notifications/${n.id}/read`,{method:'POST'})}catch{}
  }
  setItems(prev=>prev.map(x=>x.id===n.id?{...x,unread:0}:x));
  if(n.unread) setUnreadCount(v=>Math.max(0,v-1));
  setOpen(false);
  if(n.product_id) nav(`/produto/${n.product_id}`);
 };

 const readAll=async()=>{
  try{await api('/api/me/notifications/read-all',{method:'POST'});setItems(prev=>prev.map(x=>({...x,unread:0})));setUnreadCount(0)}catch{}
 };

 return <>
  <div className="notifications-menu" ref={rootRef}>
   <button className="notification-bell" type="button" onClick={()=>setOpen(v=>!v)} aria-label="Notificações" title="Notificações">
    <Bell/>{unread>0&&<span className="notification-count">{unread>99?'99+':unread}</span>}
   </button>
   {open&&<div className="notifications-dropdown">
    <div className="notifications-head"><div><b>Notificações</b><small>Novidades do ClassificaJá</small></div>{unread>0&&<button onClick={readAll}><CheckCheck/> Marcar lidas</button>}</div>
    <div className="notifications-list">
     {items.length?items.map(n=><button key={n.id} className={`notification-item ${n.unread?'unread':''}`} onClick={()=>openNotification(n)}>
      <span className="notification-icon"><Megaphone/></span>
      <span className="notification-copy"><b>{n.title}</b><small>{n.body}</small><em>{new Date(n.created_at).toLocaleString('pt-BR')}</em></span>
     </button>):<div className="notifications-empty">Nenhuma notificação por enquanto.</div>}
    </div>
   </div>}
  </div>
  {toast&&<button className="notification-toast" type="button" onClick={()=>openNotification(toast)}>
    <Megaphone/><span><b>Novo anúncio</b><small>{toast.body}</small></span>
  </button>}
 </>
}
