import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';
import type {
    IAskResponse,
    IDescriptionResponse,
    IDrawingResponse,
    IDrawingsResponse,
    IGetStatus,
    ISearchResponse,
    ISimilarResponse,
    IUploadResponse,
} from '../../types/api';

export const drawingsApi = createApi({
    reducerPath: 'drawingsApi',
    baseQuery: fetchBaseQuery({
        baseUrl: 'http://127.0.0.1:8000/api',
    }),
    tagTypes: ['Items', 'Search', 'Similar'],
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

        similarDrawings: builder.query<
            ISimilarResponse,
            {
                id: string;
                limit: number;
            }
        >({
            query: (params) => {
                return `similar/${params.id}?limit=${params.limit}`;
            },
            providesTags: (result) =>
                result
                    ? [
                          ...result.similar.map((item) => ({
                              type: 'Similar' as const,
                              id: item.id,
                          })),
                          { type: 'Similar', id: 'LIST' },
                      ]
                    : [{ type: 'Similar', id: 'LIST' }],
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

        getDescription: builder.query<IDescriptionResponse, { id: string }>({
            query: (params) => `describe/${params.id}`,
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
        }),

        getAskStatus: builder.query<IGetStatus, { id: string }>({
            query: ({ id }) => `ask/status/${id}`,
            keepUnusedDataFor: 0,
        }),
    }),
});

export const {
    useGetDrawingsQuery,
    useSearchDrawingsQuery,
    useDeleteDrawingMutation,
    useGetDrawingQuery,
    useAskQuestionMutation,
    useGetDescriptionQuery,
    useUploadDrawingMutation,
    useSimilarDrawingsQuery,
    useLazyGetAskStatusQuery,
} = drawingsApi;
