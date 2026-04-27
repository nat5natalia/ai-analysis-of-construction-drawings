import React, { type ChangeEventHandler, type FC } from 'react';

interface IInput {
    onChange?: ChangeEventHandler<HTMLInputElement>;
    value: string;
    placeholder: string;
    className?: string;
    decoration?: React.ReactNode;
}

const Input: FC<IInput> = ({
    onChange = () => {},
    placeholder,
    className = '',
    decoration = null,
    value,
}) => {
    return (
        <div className={`relative ${className}`}>
            <input
                className={`p-2 pl-3 pr-10 rounded-xl w-full ${className ? className : ''}`}
                placeholder={placeholder}
                onChange={onChange}
                value={value}
            />
            {decoration && (
                <div className="absolute right-3 top-1/2 -translate-y-1/2">
                    {decoration}
                </div>
            )}
        </div>
    );
};

export default Input;
