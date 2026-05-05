import { useParams } from 'react-router';
import { useGetDrawingQuery } from '../../store/api/drawings';
import image from '../../images/no image.jfif';
import ErrorState from '../ErrorState';
import LoadingState from '../LoadingState';
import { formatDate } from '../../utils/formatDate';

const Content = () => {
    const params = useParams<{ id: string }>();
    const { data, isError, isLoading } = useGetDrawingQuery({ id: params.id! });

    return (
        <>
            <div className="flex flex-col lg:flex-row mt-6 gap-4">
                {/* Картинка */}
                <img
                    className="w-full lg:w-3/5 rounded-lg object-contain"
                    src={image}
                    alt={image}
                />

                {/* Информация */}
                <div className="w-full lg:w-2/5 flex justify-center items-start">
                    {isError && <ErrorState />}
                    {isLoading && <LoadingState />}

                    {data && (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-y-2 gap-x-4 mt-2 lg:mt-10 w-full">
                            <div className="text-gray-500">Создано:</div>
                            <div className="text-black">
                                {formatDate(data.uploaded_at)}
                            </div>

                            <div className="text-gray-500">Название файла:</div>
                            <div className="text-black wrap-break-word">
                                {data.filename}
                            </div>

                            <div className="text-gray-500">Статус:</div>
                            <div className="text-black">{data.status}</div>
                        </div>
                    )}
                </div>
            </div>

            {/* Описание */}
            {data && data.description && (
                <p className="mt-4">
                    <span className="text-gray-500">Описание: </span>
                    <span className="wrap-break-word">{data.description}</span>
                </p>
            )}
        </>
    );
};

export default Content;
