export interface IDrawingsResponse {
    total: number;
    drawings: [
        {
            id: string;
            filename: string;
            status: string;
            uploaded_at: string;
            has_description: boolean;
        },
    ];
}

export interface ISimilarResponse {
    source_id: string;
    similar: [
        {
            id: string;
            filename: string;
            description: string;
            similarity: number;
        },
    ];
}

export interface IDrawingResponse {
    id: string;
    filename: string;
    status: string;
    uploaded_at: string;
    description: string;
    has_embedding: true;
}

export interface IUploadResponse {
    id: string;
    filename: string;
    status: 'uploaded' | 'processed';
    uploaded_at: string;
}

export interface IDescriptionResponse {
    id: string;
    description: string;
    generated_at: string;
    cached: boolean;
}

export interface ISearchResponse {
    total: number;
    results: [
        {
            id: string;
            filename: string;
            description: string;
            score: number;
        },
    ];
}

export interface IAskResponse {
    id: string;
    question: string;
    answer: string;
    answered_at: string;
}
