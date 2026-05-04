import type { FC } from 'react';

interface IPages {
    page: number;
    setPage: (value: React.SetStateAction<number>) => void;
    pagesAmount: number;
}

const Pages: FC<IPages> = ({ page, setPage, pagesAmount }) => {
    return (
        <div className="flex gap-2">
            <div
                className={`pl-2 pr-2 border-2 border-gray-300 rounded-md cursor-pointer bg-white ${page === 1 ? 'text-gray-300' : ''}`}
                onClick={() => {
                    if (page === 1) return;
                    setPage((prev) => prev - 1);
                }}
            >
                {'<'}
            </div>
            {Array.from({ length: pagesAmount }, (_, i) => (
                <div
                    key={i}
                    className={`pl-2 pr-2 border-2  rounded-md cursor-pointer bg-white ${page === i + 1 ? 'border-blue-500' : 'border-gray-300'}`}
                    onClick={() => setPage(i + 1)}
                >
                    {i + 1}
                </div>
            ))}
            <div
                className={`pl-2 pr-2 border-2 border-gray-300 rounded-md cursor-pointer bg-white ${page === pagesAmount ? 'text-gray-300' : ''}`}
                onClick={() => {
                    if (page === pagesAmount) return;
                    setPage((prev) => prev + 1);
                }}
            >
                {'>'}
            </div>
        </div>
    );
};

export default Pages;
