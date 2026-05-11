import { configureStore } from '@reduxjs/toolkit';
import { drawingsApi } from './api/drawings';

export const store = configureStore({
    reducer: {
        [drawingsApi.reducerPath]: drawingsApi.reducer,
    },
    middleware: (getDefaultMiddleware) =>
        getDefaultMiddleware().concat(drawingsApi.middleware),
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
