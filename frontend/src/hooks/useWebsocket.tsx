import type {
    BaseQueryFn,
    FetchArgs,
    FetchBaseQueryError,
    FetchBaseQueryMeta,
    QueryActionCreatorResult,
    QueryDefinition,
} from '@reduxjs/toolkit/query';
import { useEffect, useRef } from 'react';
import type { IDrawingResponse } from '../types/api';
import { toast } from 'react-toastify';

const useWebsocket = (
    params: Readonly<Partial<{ id: string }>>,
    triggerGetDrawing: (
        arg: {
            id: string;
        },
        preferCacheValue?: boolean | undefined,
    ) => QueryActionCreatorResult<
        QueryDefinition<
            {
                id: string;
            },
            BaseQueryFn<
                string | FetchArgs,
                unknown,
                FetchBaseQueryError,
                object,
                FetchBaseQueryMeta
            >,
            'Items' | 'Search' | 'Similar',
            IDrawingResponse,
            'drawingsApi',
            unknown
        >
    >,
) => {
    const wsRef = useRef<WebSocket | null>(null);
    const reconnectRef = useRef<boolean>(true);
    const reconnectTimeoutRef = useRef<number | null>(null);
    const currentWsRef = useRef<WebSocket | null>(null);

    const clearReconnectTimeout = () => {
        if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current);
            reconnectTimeoutRef.current = null;
        }
    };

    const connect = () => {
        if (!reconnectRef.current) return;

        clearReconnectTimeout();

        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }
        const ws = new WebSocket(`ws://localhost:8000/ws/${params.id}`);
        wsRef.current = ws;
        currentWsRef.current = ws;

        ws.onopen = () => {
            console.log('WS connected');
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

            if (data.status === 'completed') {
                await triggerGetDrawing({ id: params.id! });
            }

            if (data.status === 'failed') {
                toast.error('Возникла ошибка обработки чертежа');
                await triggerGetDrawing({ id: params.id! });
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
