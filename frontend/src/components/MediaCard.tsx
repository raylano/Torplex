'use client'

import Image from 'next/image'
import { MediaItem } from '@/lib/api'
import StatusBadge from './StatusBadge'
import RetryDropdown from './RetryDropdown'
import { Film, Tv, Star, Sparkles } from 'lucide-react'

interface MediaCardProps {
    item: MediaItem
    onClick?: () => void
    onRefresh?: () => void
}

export default function MediaCard({ item, onClick, onRefresh }: MediaCardProps) {
    const isShow = item.type === 'show' || item.type === 'anime_show'
    const isAnime = item.is_anime || item.type.includes('anime')

    const fallbackPoster = (
        <div className="absolute inset-0 bg-gradient-to-br from-surface-800 to-surface-900 flex items-center justify-center">
            {isShow ? <Tv size={48} className="text-gray-600" /> : <Film size={48} className="text-gray-600" />}
        </div>
    )

    return (
        <div
            className="group relative rounded-xl overflow-hidden glass card-hover cursor-pointer"
            onClick={onClick}
        >
            {/* Poster */}
            <div className="relative aspect-[2/3] bg-surface-800">
                {item.poster_url ? (
                    <Image
                        src={item.poster_url}
                        alt={item.title}
                        fill
                        sizes="(max-width: 768px) 50vw, 25vw"
                        className="object-cover transition-opacity group-hover:opacity-75"
                    />
                ) : (
                    fallbackPoster
                )}

                {/* Overlay gradient */}
                <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent" />

                {/* Status badge */}
                <div className="absolute top-2 left-2">
                    <StatusBadge status={item.state} />
                </div>

                {/* Retry dropdown - show on hover */}
                <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    <RetryDropdown
                        itemId={item.id}
                        itemType={isShow ? 'show' : 'movie'}
                        onRetryComplete={onRefresh}
                    />
                </div>

                {/* Anime badge */}
                {isAnime && (
                    <div className="absolute top-10 right-2 flex items-center gap-1 px-2 py-1 rounded-full bg-accent-500/20 border border-accent-500/30">
                        <Sparkles size={12} className="text-accent-400" />
                        <span className="text-xs text-accent-300 font-medium">Anime</span>
                    </div>
                )}

                {/* Rating */}
                {item.vote_average && (
                    <div className="absolute bottom-12 right-2 flex items-center gap-1 px-2 py-1 rounded-lg bg-black/60">
                        <Star size={12} className="text-yellow-400 fill-yellow-400" />
                        <span className="text-xs text-white font-medium">
                            {item.vote_average.toFixed(1)}
                        </span>
                    </div>
                )}

                {/* Title */}
                <div className="absolute bottom-0 left-0 right-0 p-3">
                    <h3 className="text-sm font-semibold text-white line-clamp-2 group-hover:text-primary-300 transition-colors">
                        {item.title}
                    </h3>
                    <div className="flex items-center gap-2 mt-1">
                        {isShow ? <Tv size={12} className="text-gray-400" /> : <Film size={12} className="text-gray-400" />}
                        <span className="text-xs text-gray-400">
                            {item.year || 'Unknown'}
                        </span>
                    </div>
                </div>
            </div>
        </div>
    )
}
