from flask_socketio import emit, join_room, leave_room
from flask import url_for, request
from random import choice 

from sqlalchemy import func
from collections import deque


userQueue = deque()

def register_socketio_events(socketio, db, Room):

    @socketio.on('create_room')
    def handle_create_room(data):
        # Data validation
        game = data.get('game')
        user_id = data.get('user_id')
        room_id = data.get('room_id')

        if not all([game, user_id, room_id]):
            # Handle missing data keys
            emit('error', {'message': 'Invalid data for creating a room'})
            return

        # Check if the room already exists in the database
        existing_room = Room.query.filter_by(id=room_id).first()
        

        if existing_room is None:
            try:
                # Room doesn't exist, create a new one
                room = Room(
                    id=room_id,
                    users=[user_id],  # Pass the list directly
                    symbol_class_names=["cross", "circle"],  # Pass the list directly
                    points=[0],  # Pass the dictionary directly
                    moves=[],  # Pass the list directly
                    won=False,
                    current_player=0,
                    game=game
                )
            

                db.session.add(room)
                db.session.commit()
                join_room(room_id)

                emit('room_created', {'room_id': room_id, 'user_id': user_id}, room=room_id)
                emit('room_joined', {'room_id': room_id, 'user_id': user_id, 'users': [user_id]}, room=room_id)

            except Exception as e:
                # Handle database-related exceptions
                print(f"Error committing new_room to the database: {str(e)}")
                db.session.rollback()
                emit('error', {'message': f"Error creating room: {str(e)}"})
        else:
            # Room already exists
            handle_join_room({'user_id': user_id, 'room_id': room_id, 'game': game})

    @socketio.on('join_room')
    def handle_join_room(data):
        game = data['game']
        user_id = data['user_id']
        room_id = data['room_id']

         # Fetch the room from the database
        room = Room.query.get(room_id)

        if room and len(room.users) < 2 and user_id not in room.users:
            # Make a copy of the users list before modification
            room.users = room.users.copy()
            room.users.append(user_id)

            room.points = room.points.copy()
            room.points.append(0)

            db.session.add(room)
            db.session.commit()
            
            join_room(room_id)
            
            emit('room_joined', {'room_id': room_id, 'user_id': user_id, 'users': room.users}, room=room_id)
            emit('play_game', {'game': game, 'room_id': room_id}, room=room_id)
        else:
            emit('room_maximum_capacity')




    @socketio.on('join_random')
    def handle_join_random(data):
        game = data['game']
        user_id = data['user_id']

        if user_id not in userQueue:
            userQueue.append(user_id)

        if len(userQueue) >= 2:
            player1 = userQueue.popleft()
            player2 = userQueue.popleft()

            room_id = generate_random_key()
            join_room(room_id, sid=player1)
            join_room(room_id, sid=player2)

            room = Room(
                id=room_id,
                users=[player1, player2],
                symbol_class_names=["cross", "circle"],
                points=[0, 0],
                moves=[],
                won=False,
                current_player=0,
                game=game
            )

            db.session.add(room)
            db.session.commit()

            emit('room_created', {'room_id': room_id, 'user_id': user_id}, room=room_id)
            emit('room_joined', {'room_id': room_id, 'user_id': user_id, 'users': [player1, player2]}, room=room_id)
            emit('play_game', {'game': game, 'room_id': room_id}, room=room_id)
        else:
            # Add additional handling or logging for the case when there are not enough players in the queue
            print("Waiting for more players in the queue.")



    @socketio.on('leave_room')
    def handle_leave_room(data):
        user_id = data['user_id']
        room_id = data['room_id']

        # Leave the specified room
        leave_room(room_id)

        # Emit an event to inform clients that the user left the room
        socketio.emit('user_left_room', {'user_id': user_id}, room=room_id)        

    @socketio.on('play_game')
    def handle_play_game(data):
        game = data['game']
        room_id = data['room_id']

        room_url = url_for('games.play_game', game=game, room_id=room_id)
        socketio.emit('redirect', {'url': room_url}, room=room_id)

    @socketio.on('placeSymbol')
    def handle_placeSymbol(data):
        global current_player
        
        cell_id, user_id, room_id = data.values()

        room = Room.query.get(room_id)
        
        current_player = room.current_player


        if not room.won:
            if user_id == room.users[current_player]:
                emit('updateBoard', {"cell_id" : cell_id,  "symbol_class" : room.symbol_class_names[current_player]}, broadcast=True) 
                
                room.moves = room.moves.copy()
                room.moves.append(cell_id)
                
                emit('checkWin')

                room.current_player += 1
                room.current_player %= 2
                
                db.session.add(room)
                db.session.commit()
    
    @socketio.on('resetBoard')
    def handle_resetBoard(data):
        emit('resetBoard', broadcast=True)

        room_id = data['room_id']
        room = Room.query.get(room_id)

        room.moves = []
        room.won = False
        room.current_player = 0

        db.session.add(room)
        db.session.commit()

    @socketio.on('showWinner')
    def handle_showWinner(data):
        room_id, cell_ids = data.values()
        room = Room.query.get(room_id)
        room.won = True

        emit('highlightWinner', {"cell_ids": cell_ids}, broadcast=True)

        db.session.add(room)
        db.session.commit()
  
    @socketio.on('updatePlayerPoints')
    def handle_updatePlayerPoints(data):
        room_id = data.values()
        room = Room.query.get(room_id)

        
        current_player = room.current_player
        
    
        room.points = room.points.copy()
        room.points[current_player-1] += 1

        room.current_player -= 1
        emit('displayPoints', {"points": room.points}, broadcast=True)

        db.session.add(room)
        db.session.commit()


def generate_random_key():
    characters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.~'
    random_key = ''.join(choice(characters) for _ in range(8))
    return random_key