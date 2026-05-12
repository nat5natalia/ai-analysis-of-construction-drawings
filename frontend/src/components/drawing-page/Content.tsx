import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import image from '../../images/no image.jfif';
import ErrorState from '../ErrorState';
import { formatDate } from '../../utils/formatDate';
import rehypeSanitize from 'rehype-sanitize';
import type { FC } from 'react';
import type { IDrawingResponse } from '../../types/api';

interface IContent {
    data: IDrawingResponse | undefined;
    isError: boolean;
}

const Content: FC<IContent> = ({ data, isError }) => {
    console.log(data);

    const parseBase64 = () => {
        if (!data || !data.image) return null;
        const base64 = data.image.base64[0];
        const imgSrc = `data:${data.image.content_type};base64,${base64}`;
        return imgSrc;
    };

    return (
        <div className="flex flex-col lg:h-full lg:overflow-hidden">
            <div className="flex flex-col lg:flex-row mt-6 gap-4 lg:flex-1 lg:min-h-0">
                <img
                    className="w-full lg:w-3/5 rounded-lg object-contain"
                    src={parseBase64() !== null ? parseBase64()! : undefined}
                    alt={image}
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
                        <div className="wrap-break-word">
                            {data ? data.filename : <p>Загрузка...</p>}
                        </div>

                        <div className="text-gray-500">Статус:</div>
                        <div>{data ? data.status : <p>Загрузка...</p>}</div>
                    </div>
                </div>
            </div>

            <div className="mt-4 flex flex-col lg:flex-row gap-2 lg:flex-1 lg:min-h-0 lg:overflow-hidden">
                <span className="text-gray-500 shrink-0">Описание:</span>

                <div className="wrap-break-word lg:overflow-y-auto pr-2">
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
