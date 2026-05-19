import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';
import type {
    IAskResponse,
    IDrawingResponse,
    IDrawingsResponse,
    ISearchResponse,
    IUploadResponse,
} from '../../types/api';
import { API_BASE_URL } from '../../config/api';

export const drawingsApi = createApi({
    reducerPath: 'drawingsApi',
    baseQuery: fetchBaseQuery({
        baseUrl: API_BASE_URL,
    }),
    tagTypes: ['Items', 'Search'],
    endpoints: (builder) => ({
        getDrawings: builder.query<
            IDrawingsResponse,
            {
                offset: number;
                limit: number;
            }
        >({
            query: (params) => {
                const queryString = new URLSearchParams();
                console.log('FETCHING');

                queryString.append('limit', String(params.limit));
                queryString.append('offset', String(params.offset));

                console.log(`drawings?${queryString.toString()}`);
                return `drawings?${queryString.toString()}`;
            },
            providesTags: (result) =>
                result
                    ? [
                          ...result.drawings.map((item) => ({
                              type: 'Items' as const,
                              id: item.id,
                          })),
                          { type: 'Items', id: 'LIST' },
                      ]
                    : [{ type: 'Items', id: 'LIST' }],
        }),

        searchDrawings: builder.query<
            ISearchResponse,
            {
                offset: number;
                limit: number;
                q: string;
            }
        >({
            query: (params) => {
                const queryString = new URLSearchParams();
                console.log('FETCHING');

                queryString.append('q', String(params.q));
                queryString.append('limit', String(params.limit));
                queryString.append('offset', String(params.offset));

                console.log(`search?${queryString.toString()}`);
                return `search?${queryString.toString()}`;
            },
            providesTags: (result) =>
                result
                    ? [
                          ...result.results.map((item) => ({
                              type: 'Search' as const,
                              id: item.id,
                          })),
                          { type: 'Search', id: 'LIST' },
                      ]
                    : [{ type: 'Search', id: 'LIST' }],
        }),

        getDrawing: builder.query<IDrawingResponse, { id: string }>({
            query: (params) => `drawings/${params.id}`,
            providesTags: (_result, _error, { id }) => [{ type: 'Items', id }],
        }),

        deleteDrawing: builder.mutation<{ message: string }, { id: string }>({
            query: ({ id }) => ({
                url: `drawings/${id}`,
                method: 'DELETE',
            }),
            invalidatesTags: () => [{ type: 'Items', id: 'LIST' }],
        }),

        uploadDrawing: builder.mutation<IUploadResponse, { data: FormData }>({
            query: ({ data }) => ({
                url: 'upload',
                method: 'POST',
                body: data,
            }),
            invalidatesTags: () => [{ type: 'Items', id: 'LIST' }],
        }),

        askQuestion: builder.mutation<
            IAskResponse,
            { id: string; question: string }
        >({
            query: ({ question, id }) => ({
                url: `ask/${id}`,
                method: 'POST',
                body: { question },
            }),
            invalidatesTags: (_result, _error, { id }) => [
                { type: 'Items', id },
            ],
        }),
    }),
});

export const {
    useGetDrawingsQuery,
    useSearchDrawingsQuery,
    useDeleteDrawingMutation,
    useGetDrawingQuery,
    useLazyGetDrawingQuery,
    useAskQuestionMutation,
    useUploadDrawingMutation,
} = drawingsApi;
