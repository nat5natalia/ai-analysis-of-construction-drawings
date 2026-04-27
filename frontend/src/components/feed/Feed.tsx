import ErrorState from '../ErrorState';
import Pages from './Pages';
import { useGetDrawingsQuery } from '../../store/api/drawings';
import { useEffect, useState } from 'react';
import Drawing from './Drawing';
import PostDrawing from './PostDrawing';
import SearchAccordion from './SearchAccordion';

const Feed = () => {
    const [page, setPage] = useState<number>(1);
    const { data, isError, isSuccess, isLoading, isFetching } =
        useGetDrawingsQuery({
            offset: page * 6 - 6,
            limit: 6,
        });
    const pagesAmount = (total: number | undefined) => {
        if (!total) return 0;
        return Math.ceil(total / 6);
    };
    useEffect(() => {
        console.log(data);
    }, [data]);
    return (
        <div className="bg-gray-200 h-screen w-full flex flex-col">
            <div className="p-6">
                <h1 className="font-bold text-2xl">Мои чертежи</h1>

                <p className="text-gray-500">
                    {isSuccess ? `${data.total} чертежей` : 'Загрузка...'}
                </p>
            </div>
            <SearchAccordion />
            <div className="flex ml-6 mr-6 flex-1 overflow-hidden">
                <PostDrawing />
                <div
                    className={`flex-1 p-6 flex flex-col  ${isFetching ? 'opacity-50' : ''}`}
                >
                    {isError && <ErrorState />}
                    <div className="flex-1 grid grid-cols-3 grid-rows-2 gap-4 mb-3 h-1/2">
                        {isSuccess &&
                            data.drawings.map((drawing) => {
                                return (
                                    <Drawing
                                        key={drawing.id}
                                        drawing={drawing}
                                    />
                                );
                            })}
                    </div>
                    {!isError && !isLoading && (
                        <Pages
                            page={page}
                            setPage={setPage}
                            pagesAmount={pagesAmount(data?.total)}
                        />
                    )}
                </div>
            </div>
        </div>
    );
};

export default Feed;
