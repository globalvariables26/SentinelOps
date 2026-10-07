import {useEffect} from 'react';
export function useWebSocket(onEvent){useEffect(()=>{const token=localStorage.getItem('sentinelops_token');const url=(import.meta.env.VITE_WS_URL||'ws://localhost:8000/api/ws')+`?token=${encodeURIComponent(token||'')}`;let ws;try{ws=new WebSocket(url);ws.onmessage=e=>{try{onEvent(JSON.parse(e.data))}catch{}}}catch{}return()=>ws?.close()},[onEvent])}
