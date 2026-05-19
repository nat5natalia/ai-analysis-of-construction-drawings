import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import noImage from '../../images/no image.jfif';
import ErrorState from '../ErrorState';
import { formatDate } from '../../utils/formatDate';
import rehypeSanitize from 'rehype-sanitize';
import type { FC } from 'react';
import type { IDrawingResponse } from '../../types/api';
import { MdOutlineFactCheck } from 'react-icons/md';

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

    return (
        <div className="flex flex-col lg:h-full lg:overflow-hidden">
            <div className="flex flex-col lg:flex-row mt-6 gap-4 lg:flex-1 lg:min-h-0">
                <img
                    className="w-full lg:w-3/5 rounded-lg object-contain"
                    src={imageSrc !== null ? imageSrc : noImage}
                    alt="Загруженное изображение"
                />

                <div className="w-full lg:w-2/5 flex justify-center items-start">
                    {isError && <ErrorState />}

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-y-2 gap-x-4 mt-2 lg:mt-10 w-full">
                        <div className="text-gray-500">Создано:</div>
                        <div>
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

                        <section className="sm:col-span-2 mt-4 rounded-lg border border-blue-100 bg-white/75 p-4 shadow-sm">
                            <div className="mb-3 flex items-center justify-between gap-3">
                                <div className="flex items-center gap-2 text-gray-800">
                                    <span className="flex h-8 w-8 items-center justify-center rounded-md bg-blue-100 text-blue-700">
                                        <MdOutlineFactCheck className="text-lg" />
                                    </span>
                                    <div>
                                        <h2 className="text-sm font-semibold">
                                            ГОСТы и СНиПы
                                        </h2>
                                        <p className="text-xs text-gray-500">
                                            Нормативы, найденные в чертеже
                                        </p>
                                    </div>
                                </div>

                                {hasStandards && (
                                    <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700">
                                        {standards.length}
                                    </span>
                                )}
                            </div>

                            {hasStandards ? (
                                <div className="flex flex-wrap gap-2">
                                    {standards.map((standard) => (
                                        <span
                                            key={standard}
                                            className="max-w-full break-words rounded-md border border-blue-200 bg-blue-50 px-2.5 py-1 text-sm font-medium text-blue-900 shadow-[inset_0_1px_0_rgba(255,255,255,0.65)]"
                                        >
                                            {standard}
                                        </span>
                                    ))}
                                </div>
                            ) : (
                                <p className="text-sm text-gray-500">
                                    {data?.status === 'completed'
                                        ? 'Нормативы не найдены'
                                        : 'Идет поиск нормативов'}
                                </p>
                            )}
                        </section>
                    </div>
                </div>
            </div>

            <div className="mt-4 flex flex-col lg:flex-row gap-2 lg:flex-1 lg:min-h-0 lg:overflow-hidden">
                <span className="text-gray-500 shrink-0">Описание:</span>

                <div className="break-words lg:overflow-y-auto pr-2">
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
