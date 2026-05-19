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
    const refetchDrawingRef = useRef(refetchDrawing);

    useEffect(() => {
        refetchDrawingRef.current = refetchDrawing;
    }, [refetchDrawing]);

    useEffect(() => {
        const drawingId = params.id;
        if (!drawingId) return;

        reconnectRef.current = true;

        const clearReconnectTimeout = () => {
            if (reconnectTimeoutRef.current) {
                window.clearTimeout(reconnectTimeoutRef.current);
                reconnectTimeoutRef.current = null;
            }
        };

        const connect = () => {
            if (!reconnectRef.current) return;

            clearReconnectTimeout();

            const ws = new WebSocket(buildWsUrl(`/ws/${drawingId}`));
            wsRef.current = ws;

            ws.onopen = async () => {
                console.log('WS connected');
                await refetchDrawingRef.current();
            };

            ws.onerror = (e) => {
                console.log('WS error', e);
            };

            ws.onclose = () => {
                if (wsRef.current !== ws || !reconnectRef.current) return;
                console.log('WS closed');

                clearReconnectTimeout();

                reconnectTimeoutRef.current = window.setTimeout(() => {
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

                if (data.drawing_id && data.drawing_id !== drawingId) {
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

        connect();

        const interval = window.setInterval(() => {
            if (wsRef.current?.readyState === WebSocket.OPEN) {
                wsRef.current.send('ping');
            }
        }, 50000);

        return () => {
            reconnectRef.current = false;

            wsRef.current?.close();
            wsRef.current = null;

            clearReconnectTimeout();
            window.clearInterval(interval);
        };
    }, [params.id]);
};

export default useWebsocket;
