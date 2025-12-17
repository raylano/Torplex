'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
    LayoutDashboard,
    Library,
    Search,
    Settings,
    Film,
    Tv,
    Sparkles
} from 'lucide-react'
import { clsx } from 'clsx'

const navigation = [
    { name: 'Dashboard', href: '/', icon: LayoutDashboard },
    { name: 'Library', href: '/library', icon: Library },
    { name: 'Search', href: '/search', icon: Search },
    { name: 'Settings', href: '/settings', icon: Settings },
]

export default function Sidebar() {
    const pathname = usePathname()

    return (
        <aside className="fixed left-0 top-0 h-full w-64 glass border-r border-white/10 z-50">
            <div className="flex flex-col h-full">
                {/* Logo */}
                <div className="p-6">
                    <Link href="/" className="flex items-center gap-3 group">
                        <div className="relative">
                            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-500 to-accent-500 flex items-center justify-center">
                                <Sparkles className="text-white" size={20} />
                            </div>
                            <div className="absolute inset-0 rounded-xl bg-gradient-to-br from-primary-500 to-accent-500 blur-lg opacity-50 group-hover:opacity-75 transition-opacity" />
                        </div>
                        <div>
                            <span className="text-xl font-bold gradient-text">Torplex</span>
                            <span className="block text-xs text-gray-500">Media Automation</span>
                        </div>
                    </Link>
                </div>

                {/* Navigation */}
                <nav className="flex-1 px-4 space-y-1">
                    {navigation.map((item) => {
                        const isActive = pathname === item.href

                        return (
                            <Link
                                key={item.name}
                                href={item.href}
                                className={clsx(
                                    'flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200',
                                    isActive
                                        ? 'bg-primary-500/20 text-primary-400'
                                        : 'text-gray-400 hover:bg-white/5 hover:text-white'
                                )}
                            >
                                <item.icon size={20} />
                                <span className="font-medium">{item.name}</span>
                                {isActive && (
                                    <div className="ml-auto w-1.5 h-1.5 rounded-full bg-primary-400" />
                                )}
                            </Link>
                        )
                    })}
                </nav>

                {/* Quick Stats */}
                <div className="p-4 m-4 rounded-xl bg-white/5">
                    <div className="flex items-center justify-between text-sm">
                        <div className="flex items-center gap-2 text-gray-400">
                            <Film size={16} />
                            <span>Movies</span>
                        </div>
                        <div className="flex items-center gap-2 text-gray-400">
                            <Tv size={16} />
                            <span>Shows</span>
                        </div>
                    </div>
                </div>

                {/* Version */}
                <div className="p-4 text-center text-xs text-gray-600">
                    Torplex v2.0.0
                </div>
            </div>
        </aside>
    )
}
