import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import Sidebar from '@/components/Sidebar'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
    title: 'Torplex - Media Automation',
    description: 'Your personal media automation platform with Real-Debrid & Torbox support',
}

export default function RootLayout({
    children,
}: {
    children: React.ReactNode
}) {
    return (
        <html lang="en">
            <body className={inter.className}>
                <div className="flex min-h-screen">
                    <Sidebar />
                    {/* ml-0 on mobile, ml-64 on desktop (md+) */}
                    <main className="flex-1 ml-0 md:ml-64 p-4 md:p-8 pt-16 md:pt-8">
                        {children}
                    </main>
                </div>
            </body>
        </html>
    )
}

