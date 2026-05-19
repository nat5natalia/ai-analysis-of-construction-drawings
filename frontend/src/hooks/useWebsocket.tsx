import { useEffect, useRef } from 'react';
import { toast } from 'react-toastify';
import { buildWsUrl } from '../config/api';

const useWebsocket = (
    params: Readonly<Partial<{ id: string }>>,
    refetchDrawing: () => Promise<unknown> | unknown,
) => {
    const wsRef = useRef<WebSocket | null>(null);
    const reconnectRef = useRef<boolean>(true);
    const reconnectTimeoutRef = useRef<number | null>(null);
    const currentWsRef = useRef<WebSocket | null>(null);
    const refetchDrawingRef = useRef(refetchDrawing);

    useEffect(() => {
        refetchDrawingRef.current = refetchDrawing;
    }, [refetchDrawing]);

    const clearReconnectTimeout = () => {
        if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current);
            reconnectTimeoutRef.current = null;
        }
    };

    const connect = () => {
        if (!reconnectRef.current || !params.id) return;

        clearReconnectTimeout();

        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }

        const ws = new WebSocket(buildWsUrl(`/ws/${params.id}`));
        wsRef.current = ws;
        currentWsRef.current = ws;

        ws.onopen = async () => {
            console.log('WS connected');
            await refetchDrawingRef.current();
        };

        ws.onerror = (e) => {
            console.log('WS error', e);
        };

        ws.onclose = () => {
            if (currentWsRef.current !== ws) return;
            console.log('WS closed');

            clearReconnectTimeout();

            reconnectTimeoutRef.current = setTimeout(() => {
                connect();
            }, 2000);
        };

        ws.onmessage = async (event) => {
            const raw = event.data;

            if (raw === 'pong') return;

            let data;
            try {
                data = JSON.parse(raw);
            } catch {
                return;
            }

            if (data.drawing_id && data.drawing_id !== params.id) {
                return;
            }

            if (data.event || data.status) {
                await refetchDrawingRef.current();
            }

            if (data.status === 'failed') {
                toast.error('Возникла ошибка обработки чертежа');
            }
        };
    };

    useEffect(() => {
        if (!params.id) return;

        reconnectRef.current = true;

        connect();

        const interval = setInterval(() => {
            if (wsRef.current?.readyState === WebSocket.OPEN) {
                wsRef.current.send('ping');
            }
        }, 50000);

        return () => {
            reconnectRef.current = false;

            wsRef.current?.close();

            if (reconnectTimeoutRef.current) {
                clearTimeout(reconnectTimeoutRef.current);
                reconnectTimeoutRef.current = null;
            }

            clearInterval(interval);
        };
    }, [params.id]);
};

export default useWebsocket;
