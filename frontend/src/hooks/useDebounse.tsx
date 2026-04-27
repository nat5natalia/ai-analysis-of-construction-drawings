import { useEffect, useState } from 'react';

export const useDebounce = (value: string) => {
    const [debounced, setDebounced] = useState<string>('');
    useEffect(() => {
        const timeout = setTimeout(() => {
            setDebounced(value);
        }, 300);
        return () => clearTimeout(timeout);
    }, [value]);

    return debounced;
};
