export interface IMessage {
    role: 'user' | 'assistant';
    content?: string;
    text?: string;
    ts?: string;
}

export interface ImageData {
    base64: string[];
    content_type: string;
    total_pages: number;
}

export interface IDrawingsResponse {
    total: number;
    drawings: [
        {
            id: string;
            filename: string;
            image?: ImageData | null;
            status: 'completed' | 'processing' | 'failed';
            uploaded_at: string;
            has_description: boolean;
        },
    ];
}

export interface IDrawingResponse {
    id: string;
    filename: string;
    image?: ImageData | null;
    status: 'completed' | 'processing' | 'failed';
    uploaded_at: string;
    description: string;
    has_embedding: true;
    messages?: IMessage[];
    standards?: string[];
}

export interface IUploadResponse {
    id: string;
    filename: string;
    status: 'uploaded' | 'processed';
    uploaded_at: string;
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

