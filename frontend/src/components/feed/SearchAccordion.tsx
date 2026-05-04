import { useEffect, useState, type ChangeEventHandler } from 'react';
import Input from '../../UI/Input';
import { IoMdCloseCircle, IoMdMore } from 'react-icons/io';
import Drawing from './Drawing';
import { useSearchDrawingsQuery } from '../../store/api/drawings';
import { skipToken } from '@reduxjs/toolkit/query/react';
import { useDebounce } from '../../hooks/useDebounse';
import LoadingState from '../LoadingState';
import ErrorState from '../ErrorState';

const SearchAccordion = () => {
    const [search, setSearch] = useState<string>('');
    const [page, setPage] = useState<number>(1);
    const [pagesAmount, setPagesAmount] = useState<number>(0);
    const debouncedSearch = useDebounce(search);
    const [results, setResults] = useState<
        {
            id: string;
            filename: string;
            description: string;
            score: number;
        }[]
    >([]);

    const { data, isFetching, isError } = useSearchDrawingsQuery(
        debouncedSearch.trim() !== ''
            ? { q: debouncedSearch, limit: 5, offset: page * 5 - 5 }
            : skipToken,
    );

    const searchHandler: ChangeEventHandler<HTMLInputElement> = (e) => {
        const value = e.target.value;
        setSearch(value);
    };

    /* eslint-disable-next-line react-hooks/exhaustive-deps */
    useEffect(() => {
        setResults([]);
        setPage(1);
        if (debouncedSearch === '') setPagesAmount(0);
    }, [debouncedSearch]);

    useEffect(() => {
        if (data) {
            setPagesAmount(Math.ceil(data.total / 5));
            setResults((prev) => [...prev, ...data.results]);
        }
    }, [data]);

    return (
        <div className="ml-6 mr-6 relative">
            <div
                className={`flex bg-white ${search.length > 0 ? 'rounded-t-2xl' : 'rounded-2xl'}  p-3 gap-2`}
            >
                <Input
                    value={search}
                    placeholder="Найти чертеж..."
                    className="w-full bg-gray-200 rounded-xl"
                    decoration={
                        <IoMdCloseCircle
                            className="cursor-pointer"
                            onClick={() => setSearch('')}
                        />
                    }
                    onChange={searchHandler}
                />
            </div>

            {search.length > 0 && (
                <div className="absolute top-full left-0 w-full bg-white shadow-lg rounded-b-2xl z-50 overflow-x-auto">
                    <div className="flex flex-row gap-2 p-2 h-50">
                        {isFetching && <LoadingState />}
                        {results.length === 0 && !isFetching && (
                            <div className="h-full w-full flex justify-center items-center">
                                <p className=" font-medium text-2xl">
                                    Чертежи не найдены
                                </p>
                            </div>
                        )}
                        {isError && <ErrorState />}
                        {results &&
                            results.map((item) => (
                                <div
                                    key={item.id}
                                    className={`shrink-0 px-4 py-2 bg-gray-100 rounded-lg hover:bg-gray-200 cursor-pointer whitespace-nowrap ${isFetching ? 'opacity-30' : ''}`}
                                >
                                    <Drawing drawing={item} />
                                </div>
                            ))}
                        {page < pagesAmount && !isFetching && (
                            <div className="h-full flex items-center justify-center">
                                <div
                                    onClick={() => setPage((prev) => prev + 1)}
                                    className="h-fit w-fit rounded-2xl bg-blue-500 pt-3 pb-3"
                                >
                                    <IoMdMore className="text-white text-2xl " />
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};

export default SearchAccordion;
