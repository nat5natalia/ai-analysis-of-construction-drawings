import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import noImage from '../../images/no image.jfif';
import ErrorState from '../ErrorState';
import { formatDate } from '../../utils/formatDate';
import rehypeSanitize from 'rehype-sanitize';
import type { FC, ReactNode } from 'react';
import type { IDrawingResponse } from '../../types/api';

interface IContent {
    data: IDrawingResponse | undefined;
    isError: boolean;
}

const Content: FC<IContent> = ({ data, isError }) => {
    const parseBase64 = () => {
        if (!data || !data.image) return null;
        const base64 = data.image.base64[0];
        return `data:${data.image.content_type};base64,${base64}`;
    };

    const parseStatus = (status: 'processing' | 'completed' | 'failed') => {
        switch (status) {
            case 'processing':
                return 'В обработке';
            case 'completed':
                return 'Обработан';
            case 'failed':
                return 'Ошибка';
            default:
                return status;
        }
    };

    const imageSrc = parseBase64();
    const standards = data?.standards ?? [];
    const hasStandards = standards.length > 0;
    const standardsContent: ReactNode = hasStandards ? (
        <div className="flex flex-wrap gap-x-3 gap-y-1">
            {standards.map((standard) => (
                <span
                    key={standard}
                    className="max-w-full break-words text-blue-900"
                >
                    {standard}
                </span>
            ))}
        </div>
    ) : (
        <p className="text-gray-500">
            {data?.status === 'completed'
                ? 'Нормативы не найдены'
                : 'Идет поиск нормативов'}
        </p>
    );

    return (
        <div className="flex flex-col lg:h-full lg:min-h-0 lg:overflow-hidden">
            <div className="mt-6 flex flex-col gap-4 lg:flex-row lg:flex-1 lg:min-h-0">
                <img
                    className="w-full rounded-lg object-contain lg:w-3/5"
                    src={imageSrc !== null ? imageSrc : noImage}
                    alt="Загруженное изображение"
                />

                <div className="flex w-full justify-center lg:w-2/5 lg:items-start">
                    {isError && <ErrorState />}

                    <div className="mt-2 grid w-full grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2 lg:mt-10">
                        <div className="text-gray-500">Создано:</div>
                        <div className="min-w-0">
                            {data ? (
                                formatDate(data.uploaded_at)
                            ) : (
                                <p>Загрузка...</p>
                            )}
                        </div>

                        <div className="text-gray-500">Название файла:</div>
                        <div className="break-words">
                            {data ? data.filename : <p>Загрузка...</p>}
                        </div>

                        <div className="text-gray-500">Статус:</div>
                        <div>
                            {data ? (
                                parseStatus(data.status)
                            ) : (
                                <p>Загрузка...</p>
                            )}
                        </div>
                    </div>
                </div>
            </div>

            <div className="mt-4 flex flex-col gap-2 lg:flex-1 lg:min-h-0 lg:overflow-hidden">
                <span className="shrink-0 text-gray-500">Описание:</span>

                <div className="min-h-0 overflow-y-auto break-words pr-2">
                    <aside className="mb-3 w-full rounded-md border border-blue-100 bg-white/60 p-3 sm:float-right sm:ml-4 sm:w-[min(42%,26rem)] lg:max-h-36 lg:overflow-y-auto">
                        <div className="mb-2 text-gray-500">ГОСТы и СНиПы:</div>
                        {standardsContent}
                    </aside>

                    {data?.description ? (
                        <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            rehypePlugins={[rehypeSanitize]}
                        >
                            {data.description}
                        </ReactMarkdown>
                    ) : (
                        <p>В обработке</p>
                    )}
                </div>
            </div>
        </div>
    );
};

export default Content;
