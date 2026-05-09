import { useParams } from 'react-router';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useGetDrawingQuery } from '../../store/api/drawings';
import image from '../../images/no image.jfif';
import ErrorState from '../ErrorState';
import LoadingState from '../LoadingState';
import { formatDate } from '../../utils/formatDate';
import rehypeSanitize from 'rehype-sanitize';

const Content = () => {
    const params = useParams<{ id: string }>();
    const { data, isError, isLoading } = useGetDrawingQuery({
        id: params.id!,
    });

    return (
        <div className="flex flex-col lg:h-full lg:overflow-hidden">
            <div className="flex flex-col lg:flex-row mt-6 gap-4 lg:flex-1 lg:min-h-0">
                <img
                    className="w-full lg:w-3/5 rounded-lg object-contain"
                    src={image}
                    alt={image}
                />

                <div className="w-full lg:w-2/5 flex justify-center items-start">
                    {isError && <ErrorState />}
                    {isLoading && <LoadingState />}

                    {data && (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-y-2 gap-x-4 mt-2 lg:mt-10 w-full">
                            <div className="text-gray-500">Создано:</div>
                            <div>{formatDate(data.uploaded_at)}</div>

                            <div className="text-gray-500">Название файла:</div>
                            <div className="wrap-break-word">
                                {data.filename}
                            </div>

                            <div className="text-gray-500">Статус:</div>
                            <div>{data.status}</div>
                        </div>
                    )}
                </div>
            </div>

            {data?.description && (
                <div className="mt-4 flex flex-col lg:flex-row gap-2 lg:flex-1 lg:min-h-0 lg:overflow-hidden">
                    <span className="text-gray-500 shrink-0">Описание:</span>

                    <div className="wrap-break-word lg:overflow-y-auto pr-2">
                        <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            rehypePlugins={[rehypeSanitize]}
                        >
                            {data.description}
                        </ReactMarkdown>
                    </div>
                </div>
            )}
        </div>
    );
};
export default Content;
