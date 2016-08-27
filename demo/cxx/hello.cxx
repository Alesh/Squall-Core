#include <string>
#include <csignal>
#include <iostream>
#include <squall/Dispatcher.hxx>

using std::string;
using Dispatcher = squall::Dispatcher<string>;


int main(int argc, char const *argv[]) {

    Dispatcher dispatcher(ev::default_loop(), [&dispatcher](const string &target, int revents, const void *payload) {
    	if (revents == squall::TIMER) {
	        std::cout << "Hello, " << target << "! (" << revents << ")" << std::endl;
	        return true;
        } else {
            if (revents == squall::CLEANUP)
                std::cout << "Bye, " << target << "! (" << revents << ")" << std::endl;
            else
                std::cout << "\nGot " << target << "! (" << revents << ")" << std::endl;
                dispatcher.stop();
	        return false;
        }
    });

    dispatcher.watch_timer(string("Alesh"), 1.0);
    dispatcher.watch_timer(string("World"), 3.0);
    dispatcher.watch_signal(string("SIGINT"), SIGINT);
    dispatcher.start();
    return 0;
}