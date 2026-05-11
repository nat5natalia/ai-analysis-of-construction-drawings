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
                className={`pl-2 pr-2 border border-blue-200 rounded-md  bg-white ${page === 1 ? 'text-gray-300 cursor-not-allowed' : 'cursor-pointer'}`}
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
                    className={`pl-2 pr-2 border  rounded-md cursor-pointer  ${page === i + 1 ? 'border-blue-500 bg-blue-100' : 'border-gray-300 bg-blue-50'}`}
                    onClick={() => setPage(i + 1)}
                >
                    {i + 1}
                </div>
            ))}
            <div
                className={`pl-2 pr-2 border border-blue-200 rounded-md  bg-white ${page === pagesAmount ? 'text-gray-300 cursor-not-allowed' : 'cursor-pointer'}`}
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
