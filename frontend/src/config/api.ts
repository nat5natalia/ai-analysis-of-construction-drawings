export const API_BASE_URL =
    import.meta.env.VITE_API_BASE_URL ?? '/api';

export const buildWsUrl = (path: string) => {
    const configuredBase = import.meta.env.VITE_WS_BASE_URL;

    if (configuredBase) {
        return `${configuredBase.replace(/\/$/, '')}${path}`;
    }

    const url = new URL(API_BASE_URL, window.location.origin);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    url.pathname = path;
    url.search = '';

    return url.toString();
};
