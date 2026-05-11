import type { FC } from 'react';

interface IButton {
    onClick?: (id?: number) => void;
    className?: string;
    decoration?: React.ReactNode;
    content: string;
    disabled?: boolean;
    type?: 'button' | 'submit' | 'reset' | undefined;
}

const Button: FC<IButton> = ({
    onClick,
    className = '',
    decoration,
    content,
    disabled = false,
    type,
}) => {
    return (
        <button
            onClick={() => onClick?.()}
            disabled={disabled}
            className={`flex items-center justify-center gap-2 px-4 py-2 rounded-lg  transition ${className} cursor-pointer`}
            type={type ? type : 'button'}
        >
            <span>{content}</span>
            {decoration && (
                <span className="flex items-center">{decoration}</span>
            )}
        </button>
    );
};

export default Button;
