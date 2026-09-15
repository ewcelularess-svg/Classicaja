import React,{useEffect,useState} from 'react';
import {ArrowUp, Headphones, Lightbulb, Flag, ShieldCheck} from 'lucide-react';
import {Link,useLocation} from 'react-router-dom';

export default function Footer(){
  const location=useLocation();
  const [showTop,setShowTop]=useState(false);
  const hideFooter=location.pathname.startsWith('/admin')||location.pathname.startsWith('/mensagens');

  useEffect(()=>{
    const onScroll=()=>setShowTop(window.scrollY>520);
    onScroll();
    window.addEventListener('scroll',onScroll,{passive:true});
    return()=>window.removeEventListener('scroll',onScroll);
  },[]);

  const goTop=()=>window.scrollTo({top:0,behavior:'smooth'});

  return <>
    {!hideFooter&&<footer className="site-footer">
      <div className="site-footer-accent"/>
      <div className="site-footer-inner">
        <div className="site-footer-brand">
          <img src="/logo-classificaja.png" alt="ClassificaJá"/>
          <p>Um espaço simples e seguro para anunciar, encontrar oportunidades e negociar perto de você.</p>
          <span><ShieldCheck/> Atendimento organizado pelo ClassificaJá</span>
        </div>

        <div className="site-footer-service-grid" aria-label="Canais de atendimento">
          <Link to="/atendimento?tipo=reclamacao" className="site-footer-service complaint">
            <span className="site-footer-service-icon"><Flag/></span>
            <span><b>Reclamações</b><small>Relate um problema ou experiência.</small></span>
          </Link>
          <Link to="/atendimento?tipo=suporte" className="site-footer-service support">
            <span className="site-footer-service-icon"><Headphones/></span>
            <span><b>Suporte</b><small>Precisa de ajuda? Fale com a equipe.</small></span>
          </Link>
          <Link to="/atendimento?tipo=sugestao" className="site-footer-service suggestion">
            <span className="site-footer-service-icon"><Lightbulb/></span>
            <span><b>Sugestão</b><small>Ajude a melhorar o ClassificaJá.</small></span>
          </Link>
        </div>
      </div>
      <div className="site-footer-bottom">
        <span>© {new Date().getFullYear()} ClassificaJá. Todos os direitos reservados.</span>
        <span>Feito para conectar pessoas e oportunidades.</span>
      </div>
    </footer>}

    <button type="button" className={`back-to-top ${showTop?'visible':''}`} onClick={goTop} aria-label="Voltar ao topo" title="Voltar ao topo">
      <ArrowUp/>
      <span>Topo</span>
    </button>
  </>;
}
